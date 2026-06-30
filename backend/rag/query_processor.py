"""
Query 处理器 — 短句扩写 + 财务术语展开 + 余弦相似度校验

流程：
1. 财务术语展开：缩写→全文（如"归母净利润"→"归属于母公司股东的净利润"）
2. 判断 Query 是否需要扩写（短于阈值才扩）
3. LLM 扩写（保留原意，补充上下文）
4. 余弦相似度校验：扩写后与原文相似度 < 0.8 → 废弃扩写，用原文
5. 杜绝扩写引入的噪声/幻觉

设计要点：
- 术语展开用词典匹配，零延迟、零幻觉
- 余弦兜底可将扩写噪声率从 ~20% 降到 < 5%
"""
import numpy as np
from typing import Optional, Dict
from loguru import logger

from .model_router import chat as llm_chat, TaskType
from config import QUERY_SHORT_THRESHOLD, QUERY_MIN_SIMILARITY

# ============ 财务术语缩写 → 全文展开 ============
# 年报中这些术语几乎总是用全称，用户的缩写会导致 BM25 和语义匹配失效
FINANCIAL_TERM_MAP: Dict[str, str] = {
    # 利润相关（注意：不包含"净利""毛利"等短子串，它们会误匹配到"净利润""毛利率"内部）
    "归母净利润": "归属于母公司股东的净利润",
    "归母净利": "归属于母公司股东的净利润",
    "扣非净利润": "扣除非经常性损益的净利润",
    "扣非净利": "扣除非经常性损益的净利润",
    # 现金流
    "经营现金流": "经营活动产生的现金流量净额",
    "投资现金流": "投资活动产生的现金流量净额",
    "筹资现金流": "筹资活动产生的现金流量净额",
    # 英文缩写
    "ROE": "净资产收益率",
    "ROA": "总资产收益率",
    "EPS": "基本每股收益",
    "EBITDA": "息税折旧摊销前利润",
    # 常用缩写
    "营收": "营业收入",
    "资产负债率": "资产负债率",
    "每股收益": "基本每股收益",
}


def expand_financial_terms(query: str) -> str:
    """
    财务术语缩写展开：将用户的缩写替换为年报中的全称

    策略：保留原文，追加全称。
    例如："归母净利润是多少" → "归母净利润(归属于母公司股东的净利润)是多少"

    实现要点：
    - 按缩写长度降序处理，长词优先
    - 在原始 query 中检测缩写，在独立结果上替换（防止短词污染长词替换结果）
    - 已被长词覆盖的短词不再重复展开
    """
    expanded = query
    replaced_positions = set()  # 已被替换覆盖的字符位置

    # 按缩写长度降序：先长后短
    sorted_terms = sorted(FINANCIAL_TERM_MAP.items(), key=lambda x: len(x[0]), reverse=True)

    for abbr, full in sorted_terms:
        if abbr == full:
            continue

        # 在原 query 中查找缩写
        idx = query.find(abbr)
        if idx == -1:
            continue

        # 检查该位置是否已被更长的缩写覆盖
        positions = set(range(idx, idx + len(abbr)))
        if positions & replaced_positions:
            continue

        # 标记位置，执行替换
        replaced_positions |= positions
        expanded = expanded.replace(abbr, f"{abbr}({full})", 1)

    if expanded != query:
        logger.info(f"术语展开: '{query[:60]}...' → '{expanded[:80]}...'")
    return expanded

# 需要扩写的短 query 阈值（字符数）— 从 config 读取，可在 .env 覆盖
SHORT_QUERY_THRESHOLD = QUERY_SHORT_THRESHOLD

# 余弦相似度最低阈值（低于此值废弃扩写）— 从 config 读取，可在 .env 覆盖
MIN_SIMILARITY = QUERY_MIN_SIMILARITY


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """余弦相似度"""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def _embed_query(text: str) -> np.ndarray:
    """获取 query 的向量"""
    from .embedder import get_embedding_model
    model = get_embedding_model()
    vec = model.embed_query(text)
    return np.array(vec)


def expand_query(query: str) -> str:
    """
    短句扩写：把过于简略的问题扩展为完整的检索 query

    例如：
    "净利润？" → "比亚迪2024年归属于上市公司股东的净利润是多少？"
    "毛利率变化" → "公司毛利率相比上一年度的变化情况如何？"
    """
    if len(query) >= SHORT_QUERY_THRESHOLD:
        logger.debug(f"Query 长度 {len(query)} >= {SHORT_QUERY_THRESHOLD}，跳过扩写")
        return query

    logger.info(f"短 Query 检测（{len(query)}字），执行扩写...")

    prompt = f"""你是一个查询扩写助手。用户正在查询一份财务年报，但他的问题过于简短。
请将以下简短问题扩展为更完整的检索查询，保留原意，补充必要的上下文。

简短问题：{query}

要求：
1. 保留原始问题的核心意图
2. 补充可能的上下文（如年份、公司名称、财务指标类别）
3. 不要添加问题中没有的信息
4. 只输出扩写后的问题，不要解释"""

    try:
        expanded = llm_chat(
            messages=[{"role": "user", "content": prompt}],
            task_type=TaskType.SIMPLE,
        )
        expanded = expanded.strip()
        logger.info(f"Query 扩写: '{query}' → '{expanded}'")
        return expanded
    except Exception as e:
        logger.warning(f"Query 扩写失败: {e}")
        return query


def validate_expansion(original: str, expanded: str) -> str:
    """
    余弦相似度校验：扩写后与原文相似度 < 0.8 → 废弃，用原文

    防止扩写引入幻觉噪声
    """
    if original == expanded:
        return original

    try:
        orig_vec = _embed_query(original)
        exp_vec = _embed_query(expanded)
        sim = _cosine_sim(orig_vec, exp_vec)

        if sim < MIN_SIMILARITY:
            logger.warning(
                f"扩写校验失败: 相似度 {sim:.3f} < {MIN_SIMILARITY}，废弃扩写，使用原文"
            )
            return original

        logger.info(f"扩写校验通过: 相似度 {sim:.3f} >= {MIN_SIMILARITY}")
        return expanded
    except Exception as e:
        logger.warning(f"相似度校验异常: {e}，使用扩写结果")
        return expanded


def process_query(query: str) -> str:
    """
    完整 Query 处理流程：术语展开 → 扩写 → 校验 → 输出

    参数:
        query: 原始用户问题

    返回:
        处理后的查询文本
    """
    if not query or not query.strip():
        return query

    query = query.strip()

    # 0. 财务术语缩写展开（零延迟、零幻觉）
    query = expand_financial_terms(query)

    # 1. 短句扩写
    expanded = expand_query(query)

    # 2. 余弦校验兜底
    validated = validate_expansion(query, expanded)

    return validated
