"""
Query 实体识别 + 文档路由

功能：识别 query 中的公司实体，决定搜索范围。
- 单公司 → 仅搜索该公司的文档（消除跨文档干扰）
- 多公司（对比类）→ 搜索全部文档
- 无公司 → 搜索全部文档
"""
from typing import Optional, List
from loguru import logger


# ============ 公司实体注册表 ============
# 公司名/别名 → 对应文档文件名（子串匹配）

COMPANY_REGISTRY = {
    "贵州茅台": {
        "aliases": ["茅台", "贵州茅台", "茅台股份", "贵州茅台酒", "600519"],
        "documents": ["贵州茅台2024年年报.pdf", "测试财报摘要.md"],
    },
    "比亚迪": {
        "aliases": ["比亚迪", "比亚迪股份", "BYD", "002594", "1211.HK"],
        "documents": ["比亚迪2024年年报.PDF"],
    },
    "腾讯": {
        "aliases": ["腾讯", "腾讯控股", "Tencent", "00700", "0700.HK"],
        "documents": ["腾讯控股2024年年报.pdf"],
    },
}

# 跨文档对比关键词（命中则不限定单一文档）
CROSS_DOC_PATTERNS = ["对比", "比较", "vs", "VS", "和.*哪", "哪.*和", "两家", "二者", "之间.*差异", "异同"]


def detect_company_entities(query: str) -> List[str]:
    """
    从 query 中检测提到的公司实体名

    返回: 匹配到的公司注册名列表（去重，按在 query 中出现顺序）
    """
    found = []
    for company_name, info in COMPANY_REGISTRY.items():
        for alias in info["aliases"]:
            if alias.lower() in query.lower():
                found.append(company_name)
                break  # 一个公司只计一次
    return found


def is_cross_document_query(query: str) -> bool:
    """判断是否为跨文档对比类查询"""
    import re
    for pattern in CROSS_DOC_PATTERNS:
        if re.search(pattern, query):
            return True
    return False


def resolve_document_filter(query: str) -> Optional[List[str]]:
    """
    解析 query 应搜索的文档范围

    返回:
        None → 搜索全部文档
        ["doc1.pdf", "doc2.pdf"] → 仅搜索指定文档

    决策逻辑:
    1. 跨文档对比（如"对比茅台和比亚迪"）→ 搜索全部
    2. 单公司（如"茅台营收多少"）→ 仅搜索该公司文档
    3. 无公司（如"2024年哪家公司营收最高"）→ 搜索全部
    """
    companies = detect_company_entities(query)

    if not companies:
        logger.info(f"实体路由: 未检测到公司实体 → 搜索全部文档")
        return None

    if is_cross_document_query(query) or len(companies) >= 2:
        logger.info(f"实体路由: 跨文档对比 [{', '.join(companies)}] → 搜索全部文档")
        return None

    # 单公司 → 限定文档
    company = companies[0]
    docs = COMPANY_REGISTRY[company]["documents"]
    logger.info(f"实体路由: 命中 '{company}' → 限定文档 {docs}")
    return docs


def get_all_document_names() -> List[str]:
    """获取所有已注册文档的文件名列表"""
    docs = []
    for info in COMPANY_REGISTRY.values():
        docs.extend(info["documents"])
    return docs
