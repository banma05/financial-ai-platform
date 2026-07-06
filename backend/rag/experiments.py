"""
RAG 参数对比实验 — 找到最优参数组合

实验设计：
1. chunk_size 对比：200 / 500 / 800 / 1200
2. overlap 对比：10% / 15% / 20%
3. 语义阈值对比：mean-1σ / mean-0.5σ / mean（当前 -0.5σ）
4. Query 余弦阈值对比：0.7 / 0.8 / 0.85

每项输出：recall@1/3/5、MRR、NDCG@5、平均耗时
"""
import time
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger

from .loader import load_document
from .vector_store import reset_database, add_documents
from .hybrid_search import hybrid_search
from .evaluator import batch_evaluate, recall_at_k, mrr, ndcg_at_k

# 默认测试集路径
DEFAULT_TEST_SET = str(Path(__file__).parent.parent.parent / "evaluation" / "data" / "rag_questions.json")

# 默认测试文档（如果知识库为空才自动加载）
DEFAULT_DOCS_DIR = Path(__file__).parent.parent.parent / "data" / "documents"


def _print_table(headers: List[str], rows: List[List[str]]):
    """打印对齐表格"""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    header_row = "|" + "|".join(f" {h:<{w}} " for h, w in zip(headers, col_widths)) + "|"

    print(sep)
    print(header_row)
    print(sep)
    for row in rows:
        print("|" + "|".join(f" {str(c):<{w}} " for c, w in zip(row, col_widths)) + "|")
    print(sep)


def _ensure_data_loaded() -> bool:
    """确保向量库中有数据，如果没有则自动加载"""
    from .vector_store import get_document_list
    docs = get_document_list()
    if docs:
        logger.info(f"向量库已有 {len(docs)} 个文档，跳过加载")
        return True

    if not DEFAULT_DOCS_DIR.exists():
        logger.error(f"文档目录不存在: {DEFAULT_DOCS_DIR}")
        return False

    files = list(DEFAULT_DOCS_DIR.glob("*"))
    docs_files = [f for f in files if f.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}]
    if not docs_files:
        logger.error("文档目录中没有可加载的文件")
        return False

    logger.info(f"向量库为空，自动加载 {len(docs_files)} 个文档...")
    for f in docs_files:
        try:
            pages = load_document(str(f))
            from .semantic_splitter import semantic_chunk_per_page
            chunks = semantic_chunk_per_page(pages)
            add_documents(chunks)
            logger.info(f"  已加载: {f.name} ({len(chunks)} 块)")
        except Exception as e:
            logger.error(f"  加载失败 {f.name}: {e}")

    return True


def _create_search_fn(semantic_threshold_mode: Optional[str] = None):
    """
    创建检索函数（闭包，用于传入 batch_evaluate）

    参数:
        semantic_threshold_mode: 语义阈值模式，可选 "mean-1std"/"mean-0.5std"/"mean"
    """
    def search(query: str, top_k: int = 5) -> List[dict]:
        # 如果指定了语义阈值模式，临时覆盖
        # hybrid_search 本身不涉及语义切分参数，所以这个参数主要用于 split 阶段
        return hybrid_search(query, top_k=top_k)
    return search


# ============ 实验 1: chunk_size 对比 ============

def run_chunk_size_experiment(
    chunk_sizes: List[int] = None,
    test_set_path: str = None,
) -> Dict[str, Any]:
    """
    对比不同 chunk_size 的检索效果

    注意：此实验需要重建索引，耗时较长
    """
    if chunk_sizes is None:
        chunk_sizes = [200, 500, 800, 1200]

    test_set_path = test_set_path or DEFAULT_TEST_SET

    print("\n" + "=" * 80)
    print("实验 1: chunk_size 对比")
    print(f"对比值: {chunk_sizes}")
    print("=" * 80)

    # 加载测试集
    with open(test_set_path, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    questions = test_data["questions"]

    print("\n说明：chunk_size 实验需要重建索引，使用默认 overlap=15%\n")
    print("⚠️  此实验需要重建向量库（每次换 chunk_size 都要重新切分+入库）")
    print("建议：先手动确认要对比的 chunk_size 值，然后逐个运行\n")

    results = []
    for cs in chunk_sizes:
        print(f"\n--- chunk_size={cs} ---")
        start = time.time()

        # 重建索引
        reset_database()
        # 重新切分 + 入库
        from .semantic_splitter import semantic_chunk_per_page
        docs_files = list(DEFAULT_DOCS_DIR.glob("*"))
        docs_files = [f for f in docs_files if f.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}]
        total_chunks = 0
        for f in docs_files:
            pages = load_document(str(f))
            chunks = semantic_chunk_per_page(pages, max_chunk_size=cs)
            add_documents(chunks)
            total_chunks += len(chunks)

        rebuild_time = time.time() - start

        # 逐题评测
        search_fn = _create_search_fn()
        total_r5 = 0.0
        total_mrr_val = 0.0
        total_q_time = 0.0
        for q in questions:
            q_start = time.time()
            chunks = search_fn(q["query"], top_k=5)
            q_time = time.time() - q_start
            total_q_time += q_time

            total_r5 += recall_at_k(q["query"], q.get("expected_keywords", []), chunks, k=5)["recall@k"]
            total_mrr_val += mrr(q.get("expected_keywords", []), chunks)["mrr"]

        n = len(questions)
        result = {
            "chunk_size": cs,
            "total_chunks": total_chunks,
            "rebuild_time_s": round(rebuild_time, 2),
            "avg_query_time_s": round(total_q_time / n, 3),
            "avg_recall@5": round(total_r5 / n, 4),
            "avg_mrr": round(total_mrr_val / n, 4),
        }
        results.append(result)
        print(f"  chunks={total_chunks}, R@5={result['avg_recall@5']:.1%}, MRR={result['avg_mrr']:.1%}, "
              f"rebuild={rebuild_time:.1f}s, q_time={result['avg_query_time_s']:.3f}s")

    # 打印对比表
    print("\n📊 chunk_size 对比结果:")
    _print_table(
        ["chunk_size", "chunks数", "R@5", "MRR", "重建耗时", "单次查询"],
        [[str(r["chunk_size"]),
          str(r["total_chunks"]),
          f"{r['avg_recall@5']:.1%}",
          f"{r['avg_mrr']:.1%}",
          f"{r['rebuild_time_s']:.1f}s",
          f"{r['avg_query_time_s']:.3f}s"]
         for r in results]
    )

    # 推荐
    best = max(results, key=lambda r: r["avg_recall@5"])
    print(f"\n🏆 推荐 chunk_size = {best['chunk_size']}（R@5={best['avg_recall@5']:.1%}）")

    return {"experiment": "chunk_size", "results": results, "best": best["chunk_size"]}


# ============ 实验 2: overlap 对比 ============

def run_overlap_experiment(
    overlaps: List[float] = None,
    chunk_size: int = 800,
    test_set_path: str = None,
) -> Dict[str, Any]:
    """
    对比不同 overlap 比例的检索效果
    """
    if overlaps is None:
        overlaps = [0.10, 0.15, 0.20]

    test_set_path = test_set_path or DEFAULT_TEST_SET

    print("\n" + "=" * 80)
    print("实验 2: overlap 对比")
    print(f"对比值: {[f'{o:.0%}' for o in overlaps]}（chunk_size={chunk_size}）")
    print("=" * 80)

    with open(test_set_path, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    questions = test_data["questions"]

    results = []
    for ov in overlaps:
        print(f"\n--- overlap={ov:.0%} ---")
        start = time.time()

        reset_database()
        from .semantic_splitter import semantic_chunk_per_page
        docs_files = [f for f in DEFAULT_DOCS_DIR.glob("*")
                      if f.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}]
        total_chunks = 0
        for f in docs_files:
            pages = load_document(str(f))
            chunks = semantic_chunk_per_page(pages, max_chunk_size=chunk_size, overlap_ratio=ov)
            add_documents(chunks)
            total_chunks += len(chunks)

        rebuild_time = time.time() - start

        search_fn = _create_search_fn()
        total_r5 = 0.0
        total_mrr_val = 0.0
        total_q_time = 0.0
        for q in questions:
            q_start = time.time()
            chunks = search_fn(q["query"], top_k=5)
            q_time = time.time() - q_start
            total_q_time += q_time

            total_r5 += recall_at_k(q["query"], q.get("expected_keywords", []), chunks, k=5)["recall@k"]
            total_mrr_val += mrr(q.get("expected_keywords", []), chunks)["mrr"]

        n = len(questions)
        result = {
            "overlap": f"{ov:.0%}",
            "total_chunks": total_chunks,
            "rebuild_time_s": round(rebuild_time, 2),
            "avg_query_time_s": round(total_q_time / n, 3),
            "avg_recall@5": round(total_r5 / n, 4),
            "avg_mrr": round(total_mrr_val / n, 4),
        }
        results.append(result)
        print(f"  chunks={total_chunks}, R@5={result['avg_recall@5']:.1%}, MRR={result['avg_mrr']:.1%}")

    print("\n📊 overlap 对比结果:")
    _print_table(
        ["overlap", "chunks数", "R@5", "MRR", "重建耗时", "单次查询"],
        [[r["overlap"],
          str(r["total_chunks"]),
          f"{r['avg_recall@5']:.1%}",
          f"{r['avg_mrr']:.1%}",
          f"{r['rebuild_time_s']:.1f}s",
          f"{r['avg_query_time_s']:.3f}s"]
         for r in results]
    )

    best = max(results, key=lambda r: r["avg_recall@5"])
    print(f"\n🏆 推荐 overlap = {best['overlap']}（R@5={best['avg_recall@5']:.1%}）")

    return {"experiment": "overlap", "results": results, "best": best["overlap"]}


# ============ 实验 3: 语义阈值对比 ============

def run_semantic_threshold_experiment(
    threshold_modes: List[str] = None,
    chunk_size: int = 800,
    overlap: float = 0.15,
    test_set_path: str = None,
) -> Dict[str, Any]:
    """
    对比不同语义切分阈值的检索效果

    mean-1σ: 更激进切分（更多块）
    mean-0.5σ: 当前默认
    mean: 更保守切分（更少块）
    """
    if threshold_modes is None:
        threshold_modes = ["mean-1std", "mean-0.5std", "mean"]

    test_set_path = test_set_path or DEFAULT_TEST_SET

    print("\n" + "=" * 80)
    print("实验 3: 语义阈值对比")
    print(f"对比值: {threshold_modes}")
    print("=" * 80)

    with open(test_set_path, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    questions = test_data["questions"]

    mode_labels = {
        "mean-1std": "均值-1σ（激进，块多）",
        "mean-0.5std": "均值-0.5σ（当前默认）",
        "mean": "均值（保守，块少）",
    }

    results = []
    for mode in threshold_modes:
        print(f"\n--- 语义阈值: {mode} ({mode_labels.get(mode, mode)}) ---")
        start = time.time()

        # 计算对应的 sigma_multiplier
        sigma_map = {"mean-1std": 1.0, "mean-0.5std": 0.5, "mean": 0.0}
        sigma_mul = sigma_map.get(mode, 0.5)

        reset_database()
        from .semantic_splitter import semantic_chunk_per_page as _sem_chunk

        docs_files = [f for f in DEFAULT_DOCS_DIR.glob("*")
                      if f.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}]
        total_chunks = 0
        for f in docs_files:
            pages = load_document(str(f))
            # 用 monkey-patch 方式修改阈值
            import numpy as np
            chunks = _sem_chunk_with_threshold(pages, max_chunk_size=chunk_size,
                                                overlap_ratio=overlap, sigma_mul=sigma_mul)
            add_documents(chunks)
            total_chunks += len(chunks)

        rebuild_time = time.time() - start

        search_fn = _create_search_fn()
        total_r5 = 0.0
        total_mrr_val = 0.0
        total_q_time = 0.0
        for q in questions:
            q_start = time.time()
            chunks = search_fn(q["query"], top_k=5)
            q_time = time.time() - q_start
            total_q_time += q_time

            total_r5 += recall_at_k(q["query"], q.get("expected_keywords", []), chunks, k=5)["recall@k"]
            total_mrr_val += mrr(q.get("expected_keywords", []), chunks)["mrr"]

        n = len(questions)
        result = {
            "threshold_mode": mode,
            "label": mode_labels.get(mode, mode),
            "total_chunks": total_chunks,
            "rebuild_time_s": round(rebuild_time, 2),
            "avg_query_time_s": round(total_q_time / n, 3),
            "avg_recall@5": round(total_r5 / n, 4),
            "avg_mrr": round(total_mrr_val / n, 4),
        }
        results.append(result)
        print(f"  chunks={total_chunks}, R@5={result['avg_recall@5']:.1%}, MRR={result['avg_mrr']:.1%}")

    print("\n📊 语义阈值对比结果:")
    _print_table(
        ["阈值模式", "说明", "chunks数", "R@5", "MRR", "单次查询"],
        [[r["threshold_mode"],
          r["label"],
          str(r["total_chunks"]),
          f"{r['avg_recall@5']:.1%}",
          f"{r['avg_mrr']:.1%}",
          f"{r['avg_query_time_s']:.3f}s"]
         for r in results]
    )

    best = max(results, key=lambda r: r["avg_recall@5"])
    print(f"\n🏆 推荐语义阈值 = {best['threshold_mode']}（R@5={best['avg_recall@5']:.1%}）")

    return {"experiment": "semantic_threshold", "results": results, "best": best["threshold_mode"]}


def _sem_chunk_with_threshold(
    pages: List[dict],
    min_chunk_size: int = 200,
    max_chunk_size: int = 1200,
    overlap_ratio: float = 0.15,
    sigma_mul: float = 0.5,
) -> List[dict]:
    """
    带自定义 sigma 倍率的语义切分（用于实验）
    """
    import re
    import numpy as np
    from .embedder import get_embedding_model

    all_chunks = []
    model = get_embedding_model()
    overlap_size = int(max_chunk_size * overlap_ratio)

    for page in pages:
        text = page["text"]
        sentences = re.split(r'(?<=[。！？；\n])(?![。！？；\n])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        merged = []
        for s in sentences:
            if merged and len(s) < 20:
                merged[-1] += s
            else:
                merged.append(s)
        sentences = merged

        if len(text) < max_chunk_size or len(sentences) <= 2:
            if text.strip():
                all_chunks.append({
                    "content": text.strip(),
                    "source": page["source"],
                    "page": page["page"],
                })
            continue

        try:
            embeddings = model.embed_documents(sentences)
            embeddings = np.array(embeddings)
        except Exception as e:
            logger.warning(f"Embedding 失败, 回退滑动窗口切分: {e}")
            for i in range(0, len(text), max_chunk_size - overlap_size):
                chunk = text[i:i + max_chunk_size]
                if chunk.strip():
                    all_chunks.append({
                        "content": chunk.strip(),
                        "source": page["source"],
                        "page": page["page"],
                    })
            continue

        sims = []
        for i in range(len(embeddings) - 1):
            sim = float(np.dot(embeddings[i], embeddings[i + 1]) /
                        (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[i + 1]) + 1e-8))
            sims.append(sim)

        mean_sim = np.mean(sims) if sims else 0.5
        std_sim = np.std(sims) if sims else 0.1
        threshold = mean_sim - sigma_mul * std_sim

        current = sentences[0]
        for i in range(1, len(sentences)):
            is_boundary = sims[i - 1] < threshold
            would_overflow = len(current) + len(sentences[i]) > max_chunk_size
            too_small = len(current) < min_chunk_size

            if (is_boundary and not too_small) or would_overflow:
                if current.strip():
                    all_chunks.append({
                        "content": current.strip(),
                        "source": page["source"],
                        "page": page["page"],
                    })
                if overlap_size > 0 and len(current) > overlap_size:
                    current = current[-overlap_size:] + sentences[i]
                else:
                    current = sentences[i]
            else:
                current += sentences[i]

        if current.strip():
            all_chunks.append({
                "content": current.strip(),
                "source": page["source"],
                "page": page["page"],
            })

    logger.info(f"语义切分(sigma_mul={sigma_mul}): {len(pages)}页 → {len(all_chunks)}块")
    return all_chunks


# ============ 实验 4: Query 余弦阈值对比 ============

def run_query_threshold_experiment(
    thresholds: List[float] = None,
    test_set_path: str = None,
) -> Dict[str, Any]:
    """
    对比不同 Query 余弦相似度阈值的噪声过滤效果

    阈值越低 → 更多扩写被接受（可能有噪声）
    阈值越高 → 更多扩写被拒绝（可能丢失信息）
    """
    if thresholds is None:
        thresholds = [0.7, 0.8, 0.85]

    test_set_path = test_set_path or DEFAULT_TEST_SET

    print("\n" + "=" * 80)
    print("实验 4: Query 余弦相似度阈值对比")
    print(f"对比值: {thresholds}")
    print("=" * 80)

    with open(test_set_path, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    questions = test_data["questions"]

    # 只对短 query 做实验（>=15字的问题扩写模块不会触发）
    short_questions = []
    from .query_processor import SHORT_QUERY_THRESHOLD as DEFAULT_SHORT_THRESH
    for q in questions:
        q_copy = q.copy()
        # 临时给所有问题加一个短版本用于测试扩写效果
        if len(q["query"]) >= DEFAULT_SHORT_THRESH:
            # 用原 query 的关键词构造一个短版本
            short_q = q["query"][:12] + "？"
            q_copy["short_query"] = short_q
        short_questions.append(q_copy)

    results = []
    for thresh in thresholds:
        print(f"\n--- 余弦阈值={thresh} ---")

        # 临时修改阈值
        import backend.rag.query_processor as qp
        old_threshold = qp.MIN_SIMILARITY
        qp.MIN_SIMILARITY = thresh

        try:
            search_fn = _create_search_fn()
            total_r5 = 0.0
            total_mrr_val = 0.0
            expand_count = 0
            reject_count = 0
            total_q_time = 0.0

            for q in short_questions:
                query = q.get("short_query", q["query"])
                q_start = time.time()

                # 手动调用 process_query 看扩写/校验行为
                processed = qp.process_query(query)
                if processed != query:
                    expand_count += 1
                    if qp.validate_expansion(query, processed) == query:
                        reject_count += 1

                chunks = search_fn(query, top_k=5)
                q_time = time.time() - q_start
                total_q_time += q_time

                total_r5 += recall_at_k(q["query"], q.get("expected_keywords", []), chunks, k=5)["recall@k"]
                total_mrr_val += mrr(q.get("expected_keywords", []), chunks)["mrr"]

            n = len(short_questions)
            result = {
                "cosine_threshold": thresh,
                "avg_recall@5": round(total_r5 / n, 4),
                "avg_mrr": round(total_mrr_val / n, 4),
                "avg_query_time_s": round(total_q_time / n, 3),
                "expansions": expand_count,
                "rejections": reject_count,
                "rejection_rate": f"{reject_count / max(expand_count, 1):.0%}",
            }
            results.append(result)
            print(f"  R@5={result['avg_recall@5']:.1%}, MRR={result['avg_mrr']:.1%}, "
                  f"扩写={expand_count}, 拒绝={reject_count}")
        finally:
            qp.MIN_SIMILARITY = old_threshold

    print("\n📊 Query 余弦阈值对比结果:")
    _print_table(
        ["余弦阈值", "R@5", "MRR", "扩写次数", "拒绝次数", "拒绝率"],
        [[str(r["cosine_threshold"]),
          f"{r['avg_recall@5']:.1%}",
          f"{r['avg_mrr']:.1%}",
          str(r["expansions"]),
          str(r["rejections"]),
          r["rejection_rate"]]
         for r in results]
    )

    best = max(results, key=lambda r: r["avg_recall@5"])
    print(f"\n🏆 推荐余弦阈值 = {best['cosine_threshold']}（R@5={best['avg_recall@5']:.1%}）")

    return {"experiment": "query_threshold", "results": results, "best": best["cosine_threshold"]}


# ============ 一键全跑 ============

def run_all_experiments(
    chunk_sizes: List[int] = None,
    overlaps: List[float] = None,
    threshold_modes: List[str] = None,
    cosine_thresholds: List[float] = None,
    test_set_path: str = None,
    skip_rebuild: bool = False,
) -> Dict[str, Any]:
    """
    一键运行所有参数对比实验

    参数:
        skip_rebuild: 跳过需要重建索引的实验 (1, 2, 3)
    """
    test_set_path = test_set_path or DEFAULT_TEST_SET

    if not Path(test_set_path).exists():
        logger.error(f"测试集不存在: {test_set_path}")
        logger.info("请先运行 Step 2 创建测试集，或指定正确的路径")
        return {"error": "test_set_not_found"}

    # 确保数据已加载
    if not _ensure_data_loaded():
        return {"error": "no_data_loaded"}

    all_results = {}

    if not skip_rebuild:
        all_results["chunk_size"] = run_chunk_size_experiment(
            chunk_sizes=chunk_sizes, test_set_path=test_set_path
        )
        all_results["overlap"] = run_overlap_experiment(
            overlaps=overlaps, test_set_path=test_set_path
        )
        all_results["semantic_threshold"] = run_semantic_threshold_experiment(
            threshold_modes=threshold_modes, test_set_path=test_set_path
        )

    all_results["query_threshold"] = run_query_threshold_experiment(
        thresholds=cosine_thresholds, test_set_path=test_set_path
    )

    # 汇总推荐参数
    print("\n" + "=" * 80)
    print("🏆 综合推荐参数")
    print("=" * 80)

    recommendations = {}
    for exp_name, exp_result in all_results.items():
        if "best" in exp_result:
            recommendations[exp_name] = exp_result["best"]
            print(f"  {exp_name}: {exp_result['best']}")

    all_results["recommendations"] = recommendations

    # 保存结果
    output_dir = Path(__file__).parent.parent.parent / "evaluation" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"experiments_{timestamp}.json"

    # 清理不可序列化的内容
    serializable = {
        k: v for k, v in all_results.items()
        if k in ["recommendations", "chunk_size", "overlap", "semantic_threshold", "query_threshold"]
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"\n📄 实验结果已保存: {output_path}")

    return all_results


# ============ CLI 入口 ============

if __name__ == "__main__":
    import sys

    print("RAG 参数对比实验工具")
    print("用法: python -m backend.rag.experiments [experiment_name]")
    print()
    print("可用实验:")
    print("  chunk_size    - 对比不同 chunk_size")
    print("  overlap       - 对比不同 overlap 比例")
    print("  semantic      - 对比语义切分阈值")
    print("  query         - 对比 Query 余弦阈值")
    print("  all           - 一键全跑（默认）")

    exp_name = sys.argv[1] if len(sys.argv) > 1 else "all"

    if exp_name == "chunk_size":
        run_chunk_size_experiment()
    elif exp_name == "overlap":
        run_overlap_experiment()
    elif exp_name == "semantic":
        run_semantic_threshold_experiment()
    elif exp_name == "query":
        run_query_threshold_experiment()
    else:
        run_all_experiments()
