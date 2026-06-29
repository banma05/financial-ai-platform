"""
RAG 评测模块 — 四、指标拆解

两个核心指标：
1. 上下文召回率（Context Recall）：答案所需信息是否在 Top-K 切片中
2. 忠实度（Faithfulness）：回答是否基于文档，有没有瞎编

面试要点：精准定位问题——
  召回率低 → 优化切分/检索
  忠实度低 → 优化 Prompt/加校验
"""
import re
import numpy as np
from typing import List, Tuple
from loguru import logger


def evaluate_context_recall(
    query: str,
    retrieved_chunks: List[dict],
    reference_facts: List[str],
) -> dict:
    """
    上下文召回率：答案所需的事实点有多少能在检索到的文档块中找到

    参数:
        query: 用户问题
        retrieved_chunks: 检索返回的文档块
        reference_facts: 标注的事实点列表 ["营收7771亿", "同比+15%", ...]

    返回:
        {"recall": 0.85, "found": 17, "total": 20, "missing": ["..."], ...}

    实现：
    - 用简单的关键词匹配判断 fact 是否在某 chunk 中
    - 生产环境可升级为 LLM-as-Judge
    """
    if not reference_facts:
        return {"recall": 1.0, "found": 0, "total": 0, "missing": []}

    all_text = " ".join([c["content"] for c in retrieved_chunks])
    found = []
    missing = []

    for fact in reference_facts:
        # 简单匹配：事实中的关键词是否出现在检索结果中
        # 生产环境可用 embedding 相似度或 LLM 判断
        if _fuzzy_match(fact, all_text):
            found.append(fact)
        else:
            missing.append(fact)

    recall = len(found) / len(reference_facts) if reference_facts else 1.0
    logger.info(f"上下文召回率: {recall:.1%} ({len(found)}/{len(reference_facts)})")
    if missing:
        logger.warning(f"缺失事实: {missing}")

    return {
        "recall": round(recall, 4),
        "found": len(found),
        "total": len(reference_facts),
        "found_facts": found,
        "missing_facts": missing,
    }


def evaluate_faithfulness(
    answer: str,
    retrieved_chunks: List[dict],
) -> dict:
    """
    忠实度：回答中的声明能否在检索文档中找到支撑

    原理：
    1. 把回答拆成原子声明（按句号/分号拆分）
    2. 每个声明在检索文档中找支撑
    3. 找不到支撑的 = 潜在幻觉

    参数:
        answer: LLM 生成的回答
        retrieved_chunks: 检索返回的文档块

    返回:
        {"faithfulness": 0.92, "supported": 11, "total": 12, "unsupported": [...]}
    """
    claims = _extract_claims(answer)
    if not claims:
        return {"faithfulness": 1.0, "supported": 0, "total": 0, "unsupported": []}

    all_text = " ".join([c["content"] for c in retrieved_chunks])
    supported = []
    unsupported = []

    for claim in claims:
        if _fuzzy_match(claim, all_text):
            supported.append(claim)
        else:
            unsupported.append(claim)

    faithfulness = len(supported) / len(claims)
    logger.info(f"忠实度: {faithfulness:.1%} ({len(supported)}/{len(claims)})")
    if unsupported:
        logger.warning(f"无支撑声明(疑似幻觉): {unsupported[:3]}...")

    return {
        "faithfulness": round(faithfulness, 4),
        "supported": len(supported),
        "total": len(claims),
        "supported_claims": supported,
        "unsupported_claims": unsupported,
    }


def full_evaluation(
    query: str,
    answer: str,
    retrieved_chunks: List[dict],
    reference_facts: List[str] = None,
) -> dict:
    """
    完整评测：上下文召回率 + 忠实度

    双标拆分明：
    - 召回率低 → 问题在检索/切分环节 → 优化切分策略或检索算法
    - 忠实度低 → 问题在生成环节 → 优化 Prompt 或加校验
    """
    results = {}

    if reference_facts:
        results["context_recall"] = evaluate_context_recall(
            query, retrieved_chunks, reference_facts
        )

    results["faithfulness"] = evaluate_faithfulness(answer, retrieved_chunks)

    # 汇总建议
    recall = results.get("context_recall", {}).get("recall", 1.0)
    faithfulness = results["faithfulness"]["faithfulness"]

    if recall < 0.7:
        results["suggestion"] = "召回率偏低 → 优先优化切分策略和检索算法"
    elif faithfulness < 0.8:
        results["suggestion"] = "忠实度偏低 → 优化 Prompt 模板，加强'严格基于文档'约束"
    else:
        results["suggestion"] = "RAG 质量良好"

    logger.info(f"评测总结: 召回率={recall:.1%} 忠实度={faithfulness:.1%} → {results['suggestion']}")
    return results


# ============ 辅助函数 ============

def _extract_claims(text: str) -> List[str]:
    """从回答中提取原子声明"""
    # 按标点拆分
    raw = re.split(r'[。；\n]', text)
    claims = []
    for s in raw:
        s = s.strip()
        # 过滤太短的和纯列表标记
        if len(s) >= 8 and not re.match(r'^[\d\.\-\*\s、]+$', s):
            claims.append(s)
    return claims


def _fuzzy_match(claim: str, context: str, min_overlap: int = 3) -> bool:
    """
    模糊匹配：claim 中的关键词是否出现在 context 中

    简单但实用：连续 3 个以上字符匹配即认为命中
    生产环境升级为 embedding 相似度 > 0.85
    """
    # 提取 claim 中的关键数字（财务数据核心）
    numbers = re.findall(r'\d[\d,\.]+[万亿千百]?', claim)
    for num in numbers:
        if num in context:
            return True

    # 滑动窗口匹配
    claim_clean = re.sub(r'[^一-龥a-zA-Z0-9]', '', claim)
    if len(claim_clean) < 10:
        return claim_clean in context

    # 取 claim 中最长的连续中文作为关键词
    chinese_chars = re.findall(r'[一-龥]{4,}', claim)
    matches = 0
    for chars in chinese_chars:
        if chars in context:
            matches += 1

    return matches >= min(len(chinese_chars) * 0.5, 1) if chinese_chars else False
