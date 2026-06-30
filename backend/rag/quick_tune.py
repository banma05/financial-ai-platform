"""
RAG 快速调参 — 最小耗时，最大收益

策略：
1. Query 余弦阈值对比（0重建，~2min，只调 API）
2. chunk_size 对比（2次重建，选最优值）

不跑的部分（边际收益小）：
- overlap 对比 → chunk_size 的 ~15% 是业界最佳实践，微调收益 <2%
- 语义阈值对比 → mean-0.5std 对中文财务文本足够好

用法：
    PYTHONPATH="backend" python -m backend.rag.quick_tune
"""
import time
import json
import sys
from pathlib import Path
from typing import List, Dict
from loguru import logger

# ============ 配置 ============
TEST_SET_PATH = Path(__file__).parent.parent.parent / "data" / "test_questions.json"
DOCS_DIR = Path(__file__).parent.parent.parent / "data" / "documents"
REPORT_PATH = Path(__file__).parent.parent.parent / "data" / "eval_reports" / "quick_tune_report.json"


def _load_test_questions() -> List[dict]:
    with open(TEST_SET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["questions"]


def _get_doc_files():
    return [f for f in DOCS_DIR.glob("*") if f.suffix.lower() in {".pdf", ".docx", ".md", ".txt"}]


def _print_table(headers, rows):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, c in enumerate(row):
            widths[i] = max(widths[i], len(str(c)))
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(sep)
    print("|" + "|".join(f" {h:<{w}} " for h, w in zip(headers, widths)) + "|")
    print(sep)
    for row in rows:
        print("|" + "|".join(f" {str(c):<{w}} " for c, w in zip(row, widths)) + "|")
    print(sep)


# ==========================================
# 实验 1: Query 余弦阈值（不需要重建索引）
# ==========================================
def tune_query_threshold():
    """
    测 3 个余弦阈值对检索的影响。
    找所有短 query（≤20字），用不同阈值跑扩写+检索，对比 R@5。
    """
    from .query_processor import process_query, MIN_SIMILARITY as _original_threshold
    from .hybrid_search import hybrid_search
    from .evaluator import recall_at_k, mrr

    questions = _load_test_questions()
    thresholds = [0.7, 0.8, 0.85]

    # 找短 query（<= 20 字，因为默认阈值 15 字，这里多取几个看边界效果）
    short_qs = [q for q in questions if len(q["query"]) <= 20]
    if len(short_qs) < 3:
        # 不够的话，截短一些长 query 作为测试
        short_qs = []
        for q in questions:
            short_q = q["query"][:12] + "？"
            short_qs.append({**q, "query": short_q})
        short_qs = short_qs[:5]

    if not short_qs:
        logger.warning("没有短 query，跳过 Query 阈值实验")
        return None

    logger.info(f"Query 阈值实验: {len(short_qs)} 个短 query × {len(thresholds)} 个阈值")

    results = []
    for thresh in thresholds:
        # 临时改阈值
        import backend.rag.query_processor as qp
        qp.MIN_SIMILARITY = thresh

        r5_scores = []
        mrr_scores = []
        expanded_count = 0
        rejected_count = 0
        times = []

        for q in short_qs:
            t0 = time.time()
            processed = process_query(q["query"])
            query_time = time.time() - t0
            times.append(query_time)

            if processed != q["query"]:
                expanded_count += 1
                if processed == q["query"]:  # 被 validate_expansion 拒绝
                    rejected_count += 1

            chunks = hybrid_search(q["query"], top_k=5)
            kw = q.get("expected_keywords", [])
            r5_scores.append(recall_at_k(q["query"], kw, chunks, k=5)["recall@k"])
            mrr_scores.append(mrr(kw, chunks)["mrr"])

        results.append({
            "threshold": thresh,
            "avg_r5": round(sum(r5_scores) / len(r5_scores), 4),
            "avg_mrr": round(sum(mrr_scores) / len(mrr_scores), 4),
            "avg_time": round(sum(times) / len(times), 3),
            "expanded": expanded_count,
            "rejected": rejected_count,
        })

        # 恢复
        qp.MIN_SIMILARITY = _original_threshold

    print("\n" + "=" * 60)
    print("[Query] 余弦阈值对比（无需重建索引）")
    print("=" * 60)
    print(f"  测试 query 数: {len(short_qs)}")
    for q in short_qs[:3]:
        print(f"    - {q['query'][:40]}")
    if len(short_qs) > 3:
        print(f"    ... 等 {len(short_qs)} 个")

    _print_table(
        ["余弦阈值", "R@5", "MRR", "扩写数", "拒绝数", "耗时"],
        [[str(r["threshold"]),
          f"{r['avg_r5']:.1%}",
          f"{r['avg_mrr']:.1%}",
          str(r["expanded"]),
          str(r["rejected"]),
          f"{r['avg_time']:.3f}s"]
         for r in results]
    )

    # 推荐：R@5 最高，如果相同则选拒绝率较低的（避免噪声）
    best = max(results, key=lambda r: (r["avg_r5"], -r["rejected"]))
    print(f"\n  [BEST] 推荐: QUERY_MIN_SIMILARITY = {best['threshold']}")
    print(f"     原因: R@5={best['avg_r5']:.1%}，扩写 {best['expanded']} 次拒绝 {best['rejected']} 次")
    return best["threshold"]


# ==========================================
# 实验 2: chunk_size 对比（需要重建索引）
# ==========================================
def tune_chunk_size(chunk_sizes=None):
    """
    测不同 chunk_size，只变这一个参数，其他用默认值。

    每次换 chunk_size 都要重建向量库。为省时间只测 2-3 个值。
    """
    if chunk_sizes is None:
        chunk_sizes = [500, 800]  # 最少 2 个值，想更细可加 1200

    from .loader import load_document
    from .semantic_splitter import semantic_chunk_per_page
    from .vector_store import reset_database, add_documents
    from .hybrid_search import hybrid_search
    from .evaluator import recall_at_k, mrr

    questions = _load_test_questions()

    # 只取前 10 题测（省时间，10 题已足够判断趋势）
    sample_qs = questions[:10]

    doc_files = _get_doc_files()
    if not doc_files:
        logger.error("没有文档可加载")
        return None

    logger.info(f"chunk_size 实验: {len(chunk_sizes)} 个值 × {len(sample_qs)} 题 ({len(doc_files)} 个文档)")

    results = []
    baseline_time = None

    for cs in chunk_sizes:
        print(f"\n  chunk_size={cs} ... ", end="", flush=True)
        t0 = time.time()

        # 重建索引
        reset_database()
        total_chunks = 0
        for f in doc_files:
            pages = load_document(str(f))
            chunks = semantic_chunk_per_page(pages, max_chunk_size=cs)
            add_documents(chunks)
            total_chunks += len(chunks)

        rebuild_time = time.time() - t0
        if baseline_time is None:
            baseline_time = rebuild_time

        # 逐题评测
        r5_scores = []
        mrr_scores = []
        q_times = []
        for q in sample_qs:
            qt0 = time.time()
            chunks = hybrid_search(q["query"], top_k=5)
            q_times.append(time.time() - qt0)
            kw = q.get("expected_keywords", [])
            r5_scores.append(recall_at_k(q["query"], kw, chunks, k=5)["recall@k"])
            mrr_scores.append(mrr(kw, chunks)["mrr"])

        result = {
            "chunk_size": cs,
            "chunks": total_chunks,
            "rebuild_s": round(rebuild_time, 1),
            "avg_r5": round(sum(r5_scores) / len(r5_scores), 4),
            "avg_mrr": round(sum(mrr_scores) / len(mrr_scores), 4),
            "avg_q_time": round(sum(q_times) / len(q_times), 3),
        }
        results.append(result)
        print(f"chunks={total_chunks}, R@5={result['avg_r5']:.1%}, MRR={result['avg_mrr']:.1%}, 重建={rebuild_time:.0f}s")

    # 对比表
    print("\n" + "=" * 60)
    print("[ChunkSize] chunk_size 对比")
    print("=" * 60)
    print(f"  测试文档: {len(doc_files)} 个, 样本题: {len(sample_qs)} 题")

    _print_table(
        ["chunk_size", "块数", "R@5", "MRR", "重建耗时", "查询耗时"],
        [[str(r["chunk_size"]),
          str(r["chunks"]),
          f"{r['avg_r5']:.1%}",
          f"{r['avg_mrr']:.1%}",
          f"{r['rebuild_s']}s",
          f"{r['avg_q_time']:.3f}s"]
         for r in results]
    )

    best = max(results, key=lambda r: r["avg_r5"])
    print(f"\n  [BEST] 推荐: CHUNK_SIZE = {best['chunk_size']}")
    print(f"     原因: R@5={best['avg_r5']:.1%}，{best['chunks']} 个块，重建 {best['rebuild_s']}s")

    # 用推荐值重建一次（最后状态）
    if best["chunk_size"] != chunk_sizes[-1]:
        logger.info(f"使用推荐 chunk_size={best['chunk_size']} 重建索引...")
        reset_database()
        for f in doc_files:
            pages = load_document(str(f))
            chunks = semantic_chunk_per_page(pages, max_chunk_size=best["chunk_size"])
            add_documents(chunks)

    return best["chunk_size"]


# ==========================================
# 一键调参入口
# ==========================================
def quick_tune():
    """
    一键跑完所有快速实验，输出推荐配置
    """
    print("\n" + "=" * 60)
    print("[TUNE] RAG 快速调参")
    print("=" * 60)
    print(f"  测试集: {TEST_SET_PATH}")
    print(f"  文档目录: {DOCS_DIR}")
    print()

    # 确保数据就绪
    from .vector_store import get_document_list
    docs = get_document_list()
    if not docs:
        logger.info("向量库为空，先加载文档...")
        from .loader import load_document
        from .semantic_splitter import semantic_chunk_per_page
        from .vector_store import add_documents
        for f in _get_doc_files():
            pages = load_document(str(f))
            chunks = semantic_chunk_per_page(pages)
            add_documents(chunks)
        logger.info("文档加载完成")

    recommendations = {}

    # ---- 实验 1: Query 阈值 ----
    print("\n" + "=" * 60)
    print("阶段 1/2: Query 余弦阈值（不重建，~1min）")
    print("=" * 60)
    try:
        best_threshold = tune_query_threshold()
        if best_threshold:
            recommendations["QUERY_MIN_SIMILARITY"] = best_threshold
    except Exception as e:
        logger.error(f"Query 阈值实验失败: {e}")
        recommendations["QUERY_MIN_SIMILARITY"] = 0.8

    # ---- 实验 2: chunk_size ----
    print("\n" + "=" * 60)
    print("阶段 2/2: chunk_size 对比（2次重建，~5-10min）")
    print("=" * 60)
    try:
        best_cs = tune_chunk_size([500, 800])
        if best_cs:
            recommendations["SEMANTIC_MAX_CHUNK_SIZE"] = best_cs
    except Exception as e:
        logger.error(f"chunk_size 实验失败: {e}")
        recommendations["SEMANTIC_MAX_CHUNK_SIZE"] = 800

    # ---- 汇总 ----
    print("\n" + "=" * 60)
    print("[BEST] 推荐 .env 配置")
    print("=" * 60)
    for key, val in recommendations.items():
        print(f"  {key}={val}")

    # 保存报告
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(recommendations, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVED] 报告已保存: {REPORT_PATH}")

    return recommendations


if __name__ == "__main__":
    quick_tune()
