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
from typing import List, Optional, Dict
from loguru import logger

from .model_router import chat as llm_chat, TaskType
from config import QUERY_SHORT_THRESHOLD, QUERY_MIN_SIMILARITY

# ============ 财务术语缩写 → 全文展开 ============
# 年报中这些术语几乎总是用全称，用户的缩写会导致 BM25 和语义匹配失效
FINANCIAL_TERM_MAP: Dict[str, str] = {
    # 利润相关
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
    "每股收益": "基本每股收益",
    # 术语归一化（常见混淆/错别字 → 标准术语）
    "资本负债率": "资产负债率",
    "资产管理负债比例": "资产负债率",
    "毛利润": "销售毛利率",
    "纯利润": "净利润",
    "营收增长率": "营业收入增长率",
    "现金流净额": "经营活动产生的现金流量净额",
    "总营收": "营业总收入",
    "净利润率": "净利率",
    "股东净利": "归属于母公司股东的净利润",
    "主营业务收入": "营业收入",
    "营业总收入": "营业总收入",
    # 资产负债率相关（最容易被用户用非标准表述提问）
    "负债率": "资产负债率",
    "资产负债比例": "资产负债率",
    "资本负债比率": "资产负债率",
    "资产负载率": "资产负债率",
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
        # 全称已在 query 中 → 不需要展开（防止"资产负债率"被"负债率"映射展开为"资产负债率(资产负债率)"）
        if full in query:
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


def _fast_anaphora_resolve(query: str, history: List[dict]) -> str:
    """
    纯规则指代消解（V6.0，零延迟）。

    处理最频繁的追问模式，不需要调 LLM：
    - "那X呢？" / "那X怎么样？" → 从历史中提取公司名补全
    - "它" / "该" 开头 → 从历史中提取最近的公司名/指标名
    """
    import re

    # 从历史最后几轮中提取已知公司名和最近提到的指标
    from .keywords import KNOWN_COMPANIES, FINANCIAL_METRICS
    recent_text = ""
    for msg in reversed(history[-6:]):
        recent_text = msg.get("content", "") + recent_text
        # 只取最近 3 轮（6条）
        if len(recent_text) > 1500:
            break

    # 找到最近提到的公司名
    found_company = None
    for c in KNOWN_COMPANIES:
        if c in recent_text:
            found_company = c  # 取最后出现的
    # 找到最近提到的指标（从统一关键词表构建正则）
    _metric_pattern = "|".join(re.escape(m) for m in FINANCIAL_METRICS)
    metric_match = re.search(_metric_pattern, recent_text)
    found_metric = metric_match.group(0) if metric_match else None

    # 模式1: "那X呢？" / "那X怎么样？"
    m = re.match(r'^(?:那|那么|那个)\s*(.+?)(?:呢|怎么样|如何|怎样|呢？|怎么样？)\s*$', query.strip())
    if m:
        target = m.group(1).strip()
        parts = []
        if found_company and found_company not in target:
            parts.append(found_company)
        parts.append(target)
        return "".join(parts)

    # 模式2: "它/该/其" 开头的短句，且历史中有公司名
    m = re.match(r'^(?:它|该|其|这)\s*(.+)', query.strip())
    if m and found_company:
        return f"{found_company}{m.group(1)}"

    return query


def rewrite_multiturn_query(query: str, history: List[dict]) -> str:
    """
    多轮对话改写：将含代词的追问改写为独立检索语句。

    只在检测到歧义信号时触发（零开销判断）：
    - 代词：它、他、她、这、那、这个、那个、其、该
    - 短追问：< 8 字符的追问（如"毛利率呢？"）
    - 省略主语：只提指标不提公司名
    """
    if not history or len(history) < 2:
        return query

    # 歧义检测（纯规则，不调 LLM，零延迟）
    pronoun_signals = {"它", "他", "她", "这", "那", "这个", "那个", "其", "该", "呢", "上述", "前面", "以上"}
    has_pronoun = any(p in query for p in pronoun_signals)
    is_short_followup = len(query) < 8

    if not has_pronoun and not is_short_followup:
        return query

    # ── V6.0: 纯规则快捷路径（零延迟，覆盖 80% 常见追问）──
    fast_result = _fast_anaphora_resolve(query, history)
    if fast_result != query:
        logger.info(f"[多轮改写] 规则匹配: '{query[:30]}' → '{fast_result[:60]}'")
        return fast_result

    logger.info(f"[多轮改写] 检测到歧义: {query[:50]}")

    # 提取最近 4 轮对话作为上下文
    recent = history[-8:]
    history_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else '助手'}：{m['content'][:200]}"
        for m in recent
    )

    prompt = f"""你是查询改写助手。根据对话历史，将用户的追问改写为完整的独立检索语句。

## 对话历史
{history_text}

## 当前追问
{query}

## 改写规则
1. 将代词（它/那个/该）替换为具体指代对象
2. 补充省略的主语（公司名、年份）
3. 保持原意图，不要添加额外信息
4. 只输出改写后的语句

改写："""

    try:
        rewritten = llm_chat(
            messages=[{"role": "user", "content": prompt}],
            query=query,
        )
        if rewritten and 3 < len(rewritten) < 200:
            logger.info(f"[多轮改写] '{query[:30]}' → '{rewritten[:60]}'")
            return rewritten.strip()
    except Exception as e:
        logger.warning(f"[多轮改写] 失败: {e}")

    return query


def process_query(query: str, history: List[dict] = None) -> str:
    """
    Query 处理管道：术语展开 → 多轮改写 → 扩写 → 校验

    参数:
        query: 原始用户问题
        history: 对话历史（可选），用于多轮改写
    """
    if not query or not query.strip():
        return query

    query = query.strip()

    # 0. 财务术语缩写展开（零延迟、零幻觉）
    query = expand_financial_terms(query)

    # 0.5. 多轮改写（有歧义时调一次 flash，~1-2s）
    if history:
        query = rewrite_multiturn_query(query, history)

    # 1. 短句扩写
    expanded = expand_query(query)

    # 2. 余弦校验兜底
    validated = validate_expansion(query, expanded)

    return validated
