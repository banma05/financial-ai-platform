"""
entity_router.py 单元测试

覆盖：公司实体识别、跨文档判断、文档过滤、反向文件名匹配、BM25 加权源
"""
import pytest
from rag.entity_router import (
    detect_company_entities,
    is_cross_document_query,
    resolve_document_filter,
    detect_entity_from_filename,
    get_entity_boost_sources,
    get_all_document_names,
    COMPANY_REGISTRY,
)

# ============ detect_company_entities ============


class TestDetectCompanyEntities:
    """从 query 中检测公司实体"""

    def test_单个公司_全名匹配(self):
        """查询中明确包含公司全名，应检测到"""
        result = detect_company_entities("比亚迪2024年的营业收入是多少")
        assert result == ["比亚迪"]

    def test_单个公司_别名匹配(self):
        """别名也应匹配到对应公司"""
        result = detect_company_entities("BYD的净利润增长了多少")
        assert result == ["比亚迪"]

    def test_单个公司_股票代码匹配(self):
        """股票代码别名应匹配"""
        result = detect_company_entities("002594的毛利率怎么样")
        assert result == ["比亚迪"]

    def test_多个公司_同一查询中提及两家公司(self):
        """两个不同公司的别名出现在同一查询中"""
        result = detect_company_entities("对比茅台和比亚迪的营收")
        assert "比亚迪" in result
        assert "贵州茅台" in result
        assert len(result) == 2

    def test_无公司实体(self):
        """查询中不包含任何公司实体"""
        result = detect_company_entities("2024年哪家公司营收最高")
        assert result == []

    def test_大小写不敏感(self):
        """英文别名应大小写不敏感"""
        result = detect_company_entities("byD的营收")
        assert result == ["比亚迪"]

    def test_港股代码匹配(self):
        """港股代码别名应匹配"""
        result = detect_company_entities("0700.HK的财报")
        assert result == ["腾讯"]


# ============ is_cross_document_query ============


class TestIsCrossDocumentQuery:
    """跨文档对比查询判断"""

    def test_对比关键词_对比(self):
        """包含"对比"关键词"""
        assert is_cross_document_query("对比茅台和比亚迪的营收") is True

    def test_对比关键词_比较(self):
        """包含"比较"关键词"""
        assert is_cross_document_query("比较两家公司的毛利率") is True

    def test_对比关键词_vs(self):
        """包含 vs 关键词"""
        assert is_cross_document_query("茅台 vs 比亚迪") is True

    def test_对比关键词_大小写VS(self):
        """大写 VS"""
        assert is_cross_document_query("茅台 VS 比亚迪") is True

    def test_普通查询_非对比(self):
        """普通查询不应被判定为跨文档"""
        assert is_cross_document_query("比亚迪的营收是多少") is False

    def test_普通查询_含哪但非对比(self):
        """含"哪"但不是对比模式的"""
        # "哪家公司" 不匹配 "哪.*和" 或 "和.*哪" 模式
        assert is_cross_document_query("哪家公司营收最高") is False


# ============ resolve_document_filter ============


class TestResolveDocumentFilter:
    """文档过滤范围解析"""

    def test_单公司_限定文档(self):
        """查询中只提一家公司，应限定搜索范围"""
        result = resolve_document_filter("比亚迪的营收是多少")
        assert result is not None
        assert "比亚迪2024年年报.PDF" in result

    def test_跨文档对比_返回全部(self):
        """对比类查询应返回 None（搜索全部）"""
        result = resolve_document_filter("对比茅台和比亚迪的营收")
        assert result is None

    def test_无公司实体_返回全部(self):
        """不包含公司时应返回 None"""
        result = resolve_document_filter("2024年哪家公司营收最高")
        assert result is None

    def test_两个公司_非对比关键词_返回全部(self):
        """即使没有对比关键词，提到两家公司也返回全部"""
        result = resolve_document_filter("比亚迪和茅台")
        assert result is None


# ============ detect_entity_from_filename ============


class TestDetectEntityFromFilename:
    """根据文件名反向查找公司实体"""

    def test_精确匹配_比亚迪(self):
        """文件名精确匹配"""
        result = detect_entity_from_filename("比亚迪2024年年报.PDF")
        assert result == "比亚迪"

    def test_精确匹配_茅台(self):
        """文件名精确匹配茅台"""
        result = detect_entity_from_filename("贵州茅台2024年年报.pdf")
        assert result == "贵州茅台"

    def test_包含别名(self):
        """文件名包含公司别名"""
        result = detect_entity_from_filename("Tencent-annual-report-2024.pdf")
        assert result == "腾讯"

    def test_未知文件名(self):
        """未知文件名返回 None"""
        result = detect_entity_from_filename("unknown-report.pdf")
        assert result is None

    def test_子串匹配(self):
        """短文件名中包含文档名作为子串"""
        result = detect_entity_from_filename("比亚迪2024年年报.PDF_part1")
        assert result == "比亚迪"


# ============ get_entity_boost_sources ============


class TestGetEntityBoostSources:
    """BM25 加权源文档获取"""

    def test_单公司_返回对应文档列表(self):
        """命中一个公司，返回其文档列表"""
        result = get_entity_boost_sources("比亚迪的营收")
        assert len(result) > 0
        assert "比亚迪2024年年报.PDF" in result

    def test_多公司_返回合并列表(self):
        """命中多个公司，返回所有关联文档"""
        result = get_entity_boost_sources("茅台 vs 腾讯的营收对比")
        assert len(result) >= 2

    def test_无公司_返回空列表(self):
        """未命中公司，返回空列表"""
        result = get_entity_boost_sources("什么是ROE")
        assert result == []


# ============ get_all_document_names ============


class TestGetAllDocumentNames:
    """获取所有注册文档名"""

    def test_返回非空列表(self):
        """至少返回已注册的文档"""
        result = get_all_document_names()
        assert len(result) > 0
        assert all(isinstance(d, str) for d in result)


# ============ COMPANY_REGISTRY 一致性检查 ============


class TestCompanyRegistryConsistency:
    """注册表自身数据一致性"""

    def test_每个公司至少有一个别名(self):
        for company_name, info in COMPANY_REGISTRY.items():
            assert len(info["aliases"]) > 0, f"{company_name} 缺少别名"

    def test_每个公司至少有一个文档(self):
        for company_name, info in COMPANY_REGISTRY.items():
            assert len(info["documents"]) > 0, f"{company_name} 缺少关联文档"

    def test_公司名本身在别名中(self):
        for company_name, info in COMPANY_REGISTRY.items():
            assert company_name in info["aliases"], f"{company_name} 的别名列表不包含自身"
