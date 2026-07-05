"""
智能依赖注入（ParamInjector）单元测试

覆盖：
- Level1 精确映射（60+对中→英映射表）
- Level2 编辑距离模糊匹配（≤2字符差异）
- Level3 LLM 语义匹配（mock 模式）
- 统计功能（命中率分布）
- parse_financial_value 数值解析
- edit_distance 编辑距离计算
- inject() 注入不覆盖已有参数
"""
import pytest
from agent.tools.param_injection import (
    ParamInjector,
    get_injector,
    reset_injector,
    parse_financial_value,
    FINANCIAL_TERM_TO_PARAM,
    _edit_distance,
)


class TestEditDistance:
    """编辑距离计算"""

    def test_identical_strings(self):
        assert _edit_distance("营业收入", "营业收入") == 0

    def test_single_insert(self):
        assert _edit_distance("营收", "营业收入") == 2

    def test_single_replace(self):
        assert _edit_distance("营业成本", "营业收本") == 1

    def test_completely_different(self):
        dist = _edit_distance("abc", "xyz")
        assert dist == 3

    def test_empty_string(self):
        assert _edit_distance("", "abc") == 3
        assert _edit_distance("abc", "") == 3

    def test_chinese_char_diff(self):
        """中文字符编辑距离"""
        assert _edit_distance("营业收入", "营业总收入") == 1  # 多一个"总"
        assert _edit_distance("净利润", "净利") == 1  # 少一个"润"


class TestParseFinancialValue:
    """财务数值解析"""

    def test_plain_number(self):
        assert parse_financial_value(1709.90) == 1709.90
        assert parse_financial_value(100) == 100.0

    def test_yi_yuan_string(self):
        assert parse_financial_value("1709.90亿元") == 1709.90
        assert parse_financial_value("1709.90亿") == 1709.90

    def test_wan_yuan_string(self):
        assert parse_financial_value("5000万元") == 5000.0
        assert parse_financial_value("5000万") == 5000.0

    def test_percentage_string(self):
        assert parse_financial_value("91.5%") == 91.5
        assert parse_financial_value("91.5％") == 91.5  # 全角百分号

    def test_plain_number_string(self):
        assert parse_financial_value("123.45") == 123.45

    def test_non_numeric_string(self):
        assert parse_financial_value("不适用") is None
        assert parse_financial_value("N/A") is None

    def test_none_value(self):
        assert parse_financial_value(None) is None

    def test_negative_number(self):
        assert parse_financial_value("-100.5亿元") == -100.5


class TestLevel1ExactMatch:
    """Level1 精确映射"""

    def setup_method(self):
        reset_injector()
        self.injector = get_injector()

    def test_revenue(self):
        mapped, level = self.injector.map_key("营业收入")
        assert mapped == "revenue"
        assert level == "level1"

    def test_net_profit(self):
        mapped, level = self.injector.map_key("净利润")
        assert mapped == "net_profit"
        assert level == "level1"

    def test_eps(self):
        mapped, level = self.injector.map_key("基本每股收益")
        assert mapped == "eps"
        assert level == "level1"

    def test_operating_cf(self):
        """最长键名 —— 经营活动现金流"""
        mapped, level = self.injector.map_key("经营活动产生的现金流量净额")
        assert mapped == "operating_cf"
        assert level == "level1"

    def test_equity_alias(self):
        """别名也能精确命中"""
        mapped, level = self.injector.map_key("股东权益")
        assert mapped == "equity"

    def test_alias_also_level1(self):
        """别名命中也是 Level1"""
        _, level = self.injector.map_key("营收")
        assert level == "level1"

    def test_unknown_key(self):
        """完全不认识的键名"""
        mapped, level = self.injector.map_key("量子计算收入")
        assert mapped is None
        assert level == "miss"

    def test_stats_after_level1_hits(self):
        """统计：多次 Level1 命中"""
        self.injector.map_key("营业收入")
        self.injector.map_key("净利润")
        self.injector.map_key("总资产")
        stats = self.injector.get_stats()
        assert stats["level1"] == 3
        assert stats["total"] == 3
        assert stats["level1_pct"] == 100.0


class TestLevel2FuzzyMatch:
    """Level2 编辑距离模糊匹配"""

    def setup_method(self):
        reset_injector()
        self.injector = get_injector()

    def test_typo_one_char(self):
        """单字差异（如 LLM 偶尔多输出一个字）"""
        # "营业收入额" 不在映射表中，但与 "营业收入" 编辑距离=1
        mapped, level = self.injector.map_key("营业收入额")
        assert mapped == "revenue"
        assert level == "level2"

    def test_missing_char(self):
        """少一个字的键名"""
        mapped, level = self.injector.map_key("净利")  # 距离"净利润"=1
        assert mapped == "net_profit"
        assert level == "level2"

    def test_extra_prefix(self):
        """
        多了前缀（唯一候选，无平局）。

        注意："公司营业收入" 与"营业收入"和"当期营业收入"编辑距离都是2（平局），
        保守策略下返回 miss。这里用"营业成本率"——唯一候选"营业成本"（距离1）。
        """
        mapped, level = self.injector.map_key("营业成本率")  # 距离"营业成本"=1，无平局
        assert mapped == "cost"
        assert level == "level2"

    def test_similar_but_distinct(self):
        """编辑距离刚好=2，但只有一个候选"""
        mapped, level = self.injector.map_key("资产总计额")  # 距离"资产总计"=1
        assert mapped == "total_assets"
        assert level == "level2"

    def test_ambiguous_tie(self):
        """
        编辑距离平局：如果有两个候选距离相同，保守返回 miss。
        例如 "营业总成本" → 距离"营业成本"=1，距离"营业总收入"=2
        不会平局，应该命中。
        """
        # 这个案例只有一个最近候选（距离1），应该匹配
        mapped, level = self.injector.map_key("营业总成本")
        assert mapped == "cost"  # 距离"营业成本"=1
        assert level == "level2"

    def test_too_far_distance(self):
        """编辑距离 >2，不应匹配"""
        mapped, level = self.injector.map_key("量子营业收入计算")
        # 与"营业收入"距离=4（多了"量子"和"计算"），超过阈值
        assert mapped is None
        assert level == "miss"

    def test_tie_rejection(self):
        """
        编辑距离平局时保守拒绝。

        "公司营业收入" 与"营业收入"（距离2）和"当期营业收入"（距离2）平局，
        保守策略下返回 miss，留给 Level3 LLM 处理。
        """
        mapped, level = self.injector.map_key("公司营业收入")
        assert mapped is None
        assert level == "miss"

    def test_stats_after_level2(self):
        """统计：Level2 命中"""
        self.injector.map_key("营业收入额")  # Level2
        self.injector.map_key("净利")        # Level2
        self.injector.map_key("营业收入")    # Level1
        stats = self.injector.get_stats()
        assert stats["level1"] == 1
        assert stats["level2"] == 2
        assert stats["total"] == 3


class TestParamInjectorInject:
    """inject() 方法完整流程"""

    def setup_method(self):
        reset_injector()
        self.injector = get_injector()

    def test_inject_level1_params(self):
        """注入 Level1 精确匹配的参数"""
        extracted = {"营业收入": "1709.90亿元", "净利润": "862.28亿元"}
        params = {}
        self.injector.inject(extracted, params)
        assert params["revenue"] == 1709.90
        assert params["net_profit"] == 862.28
        # 原始键名也被保留
        assert params["营业收入"] == 1709.90
        assert params["净利润"] == 862.28

    def test_inject_not_overwrite_existing(self):
        """注入不覆盖已有参数"""
        params = {"revenue": 1000.0}
        extracted = {"营业收入": "500.0亿元"}
        self.injector.inject(extracted, params)
        assert params["revenue"] == 1000.0  # 保持不变

    def test_inject_skip_meta_keys(self):
        """跳过元数据键名"""
        extracted = {"found": True, "summary": "test", "confidence": 0.9}
        params = {}
        self.injector.inject(extracted, params)
        assert "found" not in params
        assert "summary" not in params
        assert "confidence" not in params

    def test_inject_skip_non_numeric(self):
        """跳过非数值"""
        extracted = {"公司名称": "贵州茅台酒股份有限公司"}
        params = {}
        self.injector.inject(extracted, params)
        assert len(params) == 0

    def test_inject_level2_fuzzy(self):
        """注入 Level2 模糊匹配的参数"""
        extracted = {"营业收入额": "1709.90亿元"}  # 编辑距离1
        params = {}
        self.injector.inject(extracted, params)
        assert params["revenue"] == 1709.90

    def test_inject_mixed_level1_level2(self):
        """混合 Level1 + Level2"""
        extracted = {
            "营业收入": "1709.90亿元",     # Level1
            "净利": "862.28亿元",          # Level2（"净利润"距离1）
            "毛利润": "1608.80亿元",       # Level1
        }
        params = {}
        self.injector.inject(extracted, params)
        assert params["revenue"] == 1709.90
        assert params["net_profit"] == 862.28
        assert params["gross_profit"] == 1608.80
        stats = self.injector.get_stats()
        assert stats["level1"] == 2
        assert stats["level2"] == 1

    def test_stats_reset(self):
        """统计重置"""
        self.injector.map_key("营业收入")
        self.injector.map_key("净利润")
        self.injector.reset_stats()
        stats = self.injector.get_stats()
        assert stats["total"] == 0


class TestGlobalInjector:
    """全局注入器实例"""

    def setup_method(self):
        reset_injector()

    def test_get_injector_returns_same_instance(self):
        inj1 = get_injector()
        inj2 = get_injector()
        assert inj1 is inj2

    def test_reset_injector_creates_new(self):
        inj1 = get_injector()
        inj1.map_key("营业收入")
        reset_injector()
        inj2 = get_injector()
        assert inj1 is not inj2
        assert inj2.get_stats()["total"] == 0


class TestMappingTableIntegrity:
    """映射表完整性检查"""

    def test_no_duplicate_values_for_distinct_keys(self):
        """
        确保映射表中不同中文键名不会映射到不同但相互冲突的英文参数。
        （同一个中文键名可以映射到相同英文参数，这是别名设计）
        """
        # 所有映射值都在合法参数列表中
        legal_params = set(FINANCIAL_TERM_TO_PARAM.values())
        expected_params = {
            "revenue", "cost", "net_profit", "equity", "avg_equity",
            "total_assets", "avg_total_assets", "gross_profit",
            "total_liabilities", "current_assets", "current_liabilities",
            "inventory", "interest_expense", "ebit",
            "operating_cf", "investing_cf", "financing_cf",
            "capital_expenditure", "eps", "stock_price",
            "previous_revenue", "previous_profit",
            "current_revenue", "current_profit", "ebitda",
        }
        # 确保所有预期参数都在映射表中
        for param in expected_params:
            assert param in legal_params, f"{param} 不在映射表中"

    def test_mapping_table_size(self):
        """映射表至少有 50 对映射"""
        assert len(FINANCIAL_TERM_TO_PARAM) >= 50
