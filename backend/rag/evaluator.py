"""
RAG 评测 — 四维指标体系

检索指标（无需 LLM）：
1. recall@k：前 k 个文档块中期望关键词的覆盖率
2. precision@k：前 k 个文档块中命中文档的比例
3. MRR（Mean Reciprocal Rank）：第一个相关文档的排名倒数
4. NDCG@k：归一化折损累计增益

生成指标（LLM-as-Judge）：
5. 上下文召回率（Context Recall）：答案信息是否在检索的文档块中
6. 忠实度（Faithfulness）：回答是否基于文档，有没有瞎编

使用指南：
- 检索指标低 → 问题在切分/检索 → 优化 pipeline
- 生成指标低 → 问题在生成/Prompt → 加强校验
"""
import time
import json
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any
from loguru import logger


def llm_judge(prompt: str) -> str:
    """用 LLM 做评判（复用已有路由）"""
    from .model_router import chat as llm_chat, TaskType
    return llm_chat(
        messages=[{"role": "user", "content": prompt}],
        task_type=TaskType.SIMPLE,
    )


def evaluate_context_recall(
    query: str,
    answer: str,
    retrieved_chunks: List[dict],
) -> dict:
    """
    上下文召回率：答案所需信息是否在检索文档中

    用 LLM 判断：把检索到的文档拼在一起，问 LLM "这个答案能不能从这些文档推断出来"
    """
    if not retrieved_chunks:
        return {"recall": 0.0, "reason": "无检索结果"}

    context = "\n---\n".join([c["content"][:500] for c in retrieved_chunks[:5]])

    prompt = f"""你是一个 RAG 系统评测专家。请判断：以下"AI生成的答案"是否能在"检索到的文档片段"中找到支撑。

评分标准（0-100）：
- 90-100：答案中的所有关键数据/事实都能在文档中找到
- 70-89：大部分能找到，少数细节文档未覆盖
- 50-69：约一半能找到
- 30-49：少部分能找到
- 0-29：基本找不到，答案在瞎编

## 用户问题
{query}

## AI生成的答案
{answer[:800]}

## 检索到的文档片段
{context[:2000]}

请只输出一个数字（0-100）和一句话原因。格式：85|原因"""

    try:
        result = llm_judge(prompt)
        parts = result.strip().split("|", 1)
        score = int(parts[0].strip()) / 100
        reason = parts[1].strip() if len(parts) > 1 else ""
    except Exception as e:
        logger.warning(f"LLM 评测召回率失败: {e}")
        score, reason = 0.5, f"评测异常: {e}"

    logger.info(f"上下文召回率(LLM-Judge): {score:.1%}")
    return {"recall": round(score, 4), "reason": reason}


def evaluate_faithfulness(
    answer: str,
    retrieved_chunks: List[dict],
) -> dict:
    """
    忠实度：回答是否基于文档，有没有瞎编

    用 LLM 逐句检查答案中的声明能否在文档中找到支撑
    """
    if not retrieved_chunks or not answer.strip():
        return {"faithfulness": 1.0, "reason": "无内容可评"}

    context = "\n---\n".join([c["content"][:500] for c in retrieved_chunks[:5]])

    prompt = f"""你是一个 RAG 系统评测专家。请判断以下 AI 生成的回答是否严格基于检索到的文档，有没有编造文档中没有的信息。

评分标准（0-100）：
- 90-100：完全基于文档，没有任何编造
- 70-89：大部分基于文档，有些合理推断
- 50-69：有较多文档未提及的内容
- 0-49：大量编造/幻觉

## 检索到的文档片段
{context[:2000]}

## AI生成的回答
{answer[:800]}

请只输出一个数字（0-100）和一句话原因。格式：85|原因"""

    try:
        result = llm_judge(prompt)
        parts = result.strip().split("|", 1)
        score = int(parts[0].strip()) / 100
        reason = parts[1].strip() if len(parts) > 1 else ""
    except Exception as e:
        logger.warning(f"LLM 评测忠实度失败: {e}")
        score, reason = 0.5, f"评测异常: {e}"

    logger.info(f"忠实度(LLM-Judge): {score:.1%}")
    return {"faithfulness": round(score, 4), "reason": reason}


def full_evaluation(
    query: str,
    answer: str,
    retrieved_chunks: List[dict],
    reference_facts: Optional[List[str]] = None,
) -> dict:
    """
    完整评测：上下文召回率 + 忠实度

    双标拆分明：
    - 召回率低 → 优化切分策略或检索算法
    - 忠实度低 → 优化 Prompt 模板或加校验
    """
    results = {
        "context_recall": evaluate_context_recall(query, answer, retrieved_chunks),
        "faithfulness": evaluate_faithfulness(answer, retrieved_chunks),
    }

    recall = results["context_recall"]["recall"]
    faith = results["faithfulness"]["faithfulness"]

    if recall < 0.7:
        results["suggestion"] = "召回率偏低 → 优先优化切分策略和检索算法"
    elif faith < 0.8:
        results["suggestion"] = "忠实度偏低 → 优化 Prompt 模板，加强'严格基于文档'约束"
    else:
        results["suggestion"] = "RAG 质量良好"

    logger.info(f"评测: 召回率={recall:.1%} 忠实度={faith:.1%} → {results['suggestion']}")
    return results


# ============ 检索指标（无需 LLM）============

def _normalize_text(text: str) -> str:
    """
    财务文本归一化（评测用，不对检索结果做修改）：
    1. 去空白符（中文财务文档中空格不统一）
    2. 去数字千分位逗号（"1,741.44亿" → "1741.44亿"）
    3. 全角数字转半角（"１２３" → "123"）
    4. 统一中文标点（，→, 、。→. 等，防止评测关键词与chunk之间的标点差异）
    5. 百分号小数尾零归一（"91.80%" ↔ "91.8%"）
    """
    import re
    text = re.sub(r'\s+', '', text)
    # 去掉数字中的千分位逗号
    text = re.sub(r'(\d),(\d)', r'\1\2', text)
    # 全角数字/符号 → 半角
    full_to_half = str.maketrans('０１２３４５６７８９．％％', '0123456789.%%')
    text = text.translate(full_to_half)
    # 百分号小数尾零归一：91.80% → 91.8%, 91.0% → 91%
    text = re.sub(r'(\d+)\.0+%', r'\1%', text)
    text = re.sub(r'(\d+\.\d*?)0+%', r'\1%', text)
    return text


def _keyword_in_text(kw: str, text: str) -> bool:
    """检查关键词是否在文本中（忽略空白符差异）"""
    return _normalize_text(kw) in _normalize_text(text)


def recall_at_k(
    query: str,
    expected_keywords: List[str],
    retrieved_chunks: List[dict],
    k: int = 5,
) -> dict:
    """
    召回率@k：期望关键词在 top-k 检索结果中的覆盖率

    用于评估检索系统找到相关文档的能力
    """
    if not expected_keywords or not retrieved_chunks:
        return {"recall@k": 0.0, "k": k, "matched": [], "missed": expected_keywords}

    top_k = retrieved_chunks[:k]
    combined_text = " ".join([c["content"] for c in top_k])

    matched = []
    missed = []
    for kw in expected_keywords:
        if _keyword_in_text(kw, combined_text):
            matched.append(kw)
        else:
            missed.append(kw)

    recall = len(matched) / len(expected_keywords) if expected_keywords else 0.0
    return {
        "recall@k": round(recall, 4),
        "k": k,
        "matched": matched,
        "missed": missed,
    }


def precision_at_k(
    expected_keywords: List[str],
    retrieved_chunks: List[dict],
    k: int = 5,
) -> dict:
    """
    精确率@k：top-k 中有多少块至少包含一个期望关键词
    """
    if not expected_keywords or not retrieved_chunks:
        return {"precision@k": 0.0, "k": k}

    top_k = retrieved_chunks[:k]
    hit_count = 0
    for chunk in top_k:
        if any(_keyword_in_text(kw, chunk["content"]) for kw in expected_keywords):
            hit_count += 1

    precision = hit_count / k if k > 0 else 0.0
    return {
        "precision@k": round(precision, 4),
        "k": k,
        "hits": hit_count,
    }


def mrr(
    expected_keywords: List[str],
    retrieved_chunks: List[dict],
) -> dict:
    """
    MRR（Mean Reciprocal Rank）：第一个相关文档的排名倒数

    MRR 越高说明相关文档排得越靠前
    """
    if not expected_keywords or not retrieved_chunks:
        return {"mrr": 0.0, "first_rank": None}

    for rank, chunk in enumerate(retrieved_chunks, start=1):
        if any(_keyword_in_text(kw, chunk["content"]) for kw in expected_keywords):
            return {"mrr": round(1.0 / rank, 4), "first_rank": rank}

    return {"mrr": 0.0, "first_rank": None}


def ndcg_at_k(
    expected_keywords: List[str],
    retrieved_chunks: List[dict],
    k: int = 5,
) -> dict:
    """
    NDCG@k：归一化折损累计增益

    越靠前的文档命中 → 分数越高
    """
    if not expected_keywords or not retrieved_chunks:
        return {"ndcg@k": 0.0, "k": k}

    import math
    top_k = retrieved_chunks[:k]

    # DCG
    dcg = 0.0
    for i, chunk in enumerate(top_k, start=1):
        relevance = 0
        content = chunk["content"]
        # 简单二值相关度：命中的关键词越多得分越高
        relevance = sum(1 for kw in expected_keywords if _keyword_in_text(kw, content))
        if relevance > 0:
            dcg += relevance / math.log2(i + 1)

    # IDCG（理想排序，所有关键词都命中）
    idcg = 0.0
    total_relevance = len(expected_keywords)
    for i in range(1, min(k, total_relevance) + 1):
        idcg += 1.0 / math.log2(i + 1)

    ndcg = dcg / idcg if idcg > 0 else 0.0
    return {"ndcg@k": round(ndcg, 4), "k": k, "dcg": round(dcg, 4)}


def evaluate_retrieval(
    query: str,
    expected_keywords: List[str],
    retrieved_chunks: List[dict],
    k_values: List[int] = [1, 3, 5],
) -> dict:
    """
    一站式检索评测：计算所有检索指标
    """
    metrics = {}
    for k in k_values:
        metrics[f"recall@{k}"] = recall_at_k(query, expected_keywords, retrieved_chunks, k)["recall@k"]
        metrics[f"precision@{k}"] = precision_at_k(expected_keywords, retrieved_chunks, k)["precision@k"]
        metrics[f"ndcg@{k}"] = ndcg_at_k(expected_keywords, retrieved_chunks, k)["ndcg@k"]

    mrr_result = mrr(expected_keywords, retrieved_chunks)
    metrics["mrr"] = mrr_result["mrr"]
    metrics["first_rank"] = mrr_result.get("first_rank")

    return metrics


# ============ 批量评测 ============

def batch_evaluate(
    test_set_path: str,
    search_fn: Callable[[str, int], List[dict]],
    top_k: int = 5,
    verbose: bool = True,
) -> dict:
    """
    批量评测：用标准测试集评估检索系统

    参数:
        test_set_path: 测试集 JSON 文件路径
        search_fn: 检索函数，签名为 (query: str, top_k: int) -> List[dict]
        top_k: 检索返回数量
        verbose: 是否打印每题的详细结果

    返回:
        包含汇总指标和逐题详情的评测报告
    """
    test_path = Path(test_set_path)
    if not test_path.exists():
        raise FileNotFoundError(f"测试集文件不存在: {test_set_path}")

    with open(test_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    if not questions:
        raise ValueError("测试集中没有题目")

    logger.info(f"开始批量评测：{len(questions)} 题，top_k={top_k}")
    start_time = time.time()

    results = []
    total_recall_1 = 0.0
    total_recall_3 = 0.0
    total_recall_5 = 0.0
    total_mrr = 0.0
    total_ndcg_5 = 0.0
    total_time = 0.0

    for q in questions:
        q_start = time.time()
        query = q["query"]
        expected_kw = q.get("expected_keywords", [])

        # 执行检索
        chunks = search_fn(query, top_k=top_k)
        q_time = time.time() - q_start

        # 计算指标
        r1 = recall_at_k(query, expected_kw, chunks, k=1)["recall@k"]
        r3 = recall_at_k(query, expected_kw, chunks, k=3)["recall@k"]
        r5 = recall_at_k(query, expected_kw, chunks, k=5)["recall@k"]
        m = mrr(expected_kw, chunks)["mrr"]
        n5 = ndcg_at_k(expected_kw, chunks, k=5)["ndcg@k"]

        total_recall_1 += r1
        total_recall_3 += r3
        total_recall_5 += r5
        total_mrr += m
        total_ndcg_5 += n5
        total_time += q_time

        q_result = {
            "id": q["id"],
            "query": query[:80],
            "category": q.get("category", ""),
            "difficulty": q.get("difficulty", ""),
            "recall@1": r1,
            "recall@3": r3,
            "recall@5": r5,
            "mrr": m,
            "ndcg@5": n5,
            "time": round(q_time, 3),
            "chunks_found": len(chunks),
        }
        results.append(q_result)

        if verbose:
            status = "✅" if r5 >= 0.5 else ("⚠️" if r5 >= 0.3 else "❌")
            logger.info(
                f"{status} {q['id']} [{q['difficulty']}] {query[:50]}... "
                f"R@5={r5:.1%} MRR={m:.1%}"
            )

    n = len(questions)
    total_elapsed = time.time() - start_time

    report = {
        "meta": {
            "test_set": test_set_path,
            "num_questions": n,
            "top_k": top_k,
            "total_time": round(total_elapsed, 2),
            "avg_time_per_query": round(total_time / n, 3) if n > 0 else 0,
        },
        "summary": {
            "avg_recall@1": round(total_recall_1 / n, 4),
            "avg_recall@3": round(total_recall_3 / n, 4),
            "avg_recall@5": round(total_recall_5 / n, 4),
            "avg_mrr": round(total_mrr / n, 4),
            "avg_ndcg@5": round(total_ndcg_5 / n, 4),
        },
        "by_difficulty": {},
        "by_category": {},
        "details": results,
    }

    # 按难度分组统计
    for diff in ["easy", "medium", "hard"]:
        diff_results = [r for r in results if r["difficulty"] == diff]
        if diff_results:
            report["by_difficulty"][diff] = {
                "count": len(diff_results),
                "avg_recall@5": round(sum(r["recall@5"] for r in diff_results) / len(diff_results), 4),
                "avg_mrr": round(sum(r["mrr"] for r in diff_results) / len(diff_results), 4),
            }

    # 按类别分组统计
    categories = set(r["category"] for r in results)
    for cat in categories:
        cat_results = [r for r in results if r["category"] == cat]
        if cat_results:
            report["by_category"][cat] = {
                "count": len(cat_results),
                "avg_recall@5": round(sum(r["recall@5"] for r in cat_results) / len(cat_results), 4),
                "avg_mrr": round(sum(r["mrr"] for r in cat_results) / len(cat_results), 4),
            }

    logger.info(
        f"评测完成 | R@1={report['summary']['avg_recall@1']:.1%} "
        f"R@3={report['summary']['avg_recall@3']:.1%} "
        f"R@5={report['summary']['avg_recall@5']:.1%} "
        f"MRR={report['summary']['avg_mrr']:.1%} "
        f"NDCG@5={report['summary']['avg_ndcg@5']:.1%}"
    )

    return report


# ============ 语义评测（补充关键词评测，捕获术语差异）============

def semantic_recall_at_k(
    query: str,
    retrieved_chunks: List[dict],
    k: int = 5,
    sim_threshold: float = 0.5,
) -> dict:
    """
    语义召回率@k：基于 query-chunk 余弦相似度，不依赖关键词

    设计动机：关键词评测对术语差异敏感（如"资本负债率" vs chunk 中的"资产负债率"），
    语义评测直接用向量相似度判断相关性，更鲁棒。

    与关键词评测互补使用：
    - 关键词 R@5 高 + 语义 R@5 高 → 检索质量好
    - 关键词 R@5 低 + 语义 R@5 高 → 关键词标注不全，检索实际 OK
    - 关键词 R@5 高 + 语义 R@5 低 → 关键词太宽泛，实际语义不匹配
    """
    if not retrieved_chunks:
        return {"semantic_recall@k": 0.0, "k": k, "avg_similarity": 0.0}

    import numpy as np
    from .embedder import get_embedding_model

    model = get_embedding_model()
    q_vec = model.embed_query(query)
    q_vec = np.array(q_vec)

    top_k = retrieved_chunks[:k]
    similarities = []
    relevant_count = 0

    for chunk in top_k:
        c_vec = model.embed_query(chunk["content"][:1000])  # 截断长 chunk
        c_vec = np.array(c_vec)
        sim = float(np.dot(q_vec, c_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(c_vec) + 1e-8))
        similarities.append(sim)
        if sim >= sim_threshold:
            relevant_count += 1

    avg_sim = float(np.mean(similarities)) if similarities else 0.0

    return {
        "semantic_recall@k": round(relevant_count / k, 4) if k > 0 else 0.0,
        "k": k,
        "relevant_chunks": relevant_count,
        "avg_similarity": round(avg_sim, 4),
        "all_similarities": [round(s, 4) for s in similarities],
    }


# ============ 评测报告持久化 ============

_eval_report_cache: Optional[dict] = None


def get_latest_report() -> Optional[dict]:
    """获取最近一次评测报告"""
    return _eval_report_cache


def save_report(report: dict, output_path: Optional[str] = None) -> str:
    """
    保存评测报告到文件，并缓存为"最近一次报告"

    参数:
        report: 评测报告 dict
        output_path: 输出路径，默认为 data/eval_reports/ 下按时间戳命名

    返回:
        输出文件路径
    """
    global _eval_report_cache
    _eval_report_cache = report

    if output_path is None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(__file__).parent.parent.parent / "data" / "eval_reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"eval_{timestamp}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"评测报告已保存: {output_path}")
    return output_path
