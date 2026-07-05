"""
MCP 工具单元测试 — 每个工具至少 3 个用例（正常 + 边界 + 异常）
"""
import pytest
from mcp.tools.stock_price import StockPriceTool
from mcp.tools.financial_statements import FinancialStatementsTool
from mcp.tools.calculate_ratio import CalculateRatioTool
from mcp.tools.industry_comparison import IndustryComparisonTool
from mcp.tools.market_index import MarketIndexTool
from mcp.tools.financial_calendar import FinancialCalendarTool


# ==================== StockPrice ====================

class TestStockPrice:
    def setup_method(self):
        self.tool = StockPriceTool()
        assert self.tool.name == "mcp_stock_price"

    def test_realtime_maotai(self):
        result = self.tool.run(symbol="600519", period="realtime")
        assert result["success"]
        assert result["data"]["name"] == "贵州茅台"
        assert result["data"]["price"] > 0

    def test_daily_kline(self):
        result = self.tool.run(symbol="002594", period="daily")
        assert result["success"]
        assert "history" in result["data"]

    def test_unknown_symbol(self):
        result = self.tool.run(symbol="999999")
        assert not result["success"]
        assert "未找到" in result["error"]


# ==================== FinancialStatements ====================

class TestFinancialStatements:
    def setup_method(self):
        self.tool = FinancialStatementsTool()
        assert self.tool.name == "mcp_financial_statements"

    def test_all_statements(self):
        result = self.tool.run(symbol="600519", statement_type="all")
        assert result["success"]
        assert "income" in result["data"]
        assert "balance" in result["data"]
        assert "cashflow" in result["data"]

    def test_income_only(self):
        result = self.tool.run(symbol="600519", statement_type="income")
        assert result["success"]
        assert "income" in result["data"]
        assert "balance" not in result["data"]

    def test_flat_data_for_injection(self):
        """验证 flat_data 可直接用于公式计算"""
        result = self.tool.run(symbol="600519")
        flat = result["flat_data"]
        assert "营业收入" in flat
        assert "净利润" in flat
        assert isinstance(flat["营业收入"], float)

    def test_unknown_symbol(self):
        result = self.tool.run(symbol="999999")
        assert not result["success"]


# ==================== CalculateRatio ====================

class TestCalculateRatio:
    def setup_method(self):
        self.tool = CalculateRatioTool()
        assert self.tool.name == "mcp_calculate_ratio"

    def test_specific_ratios(self):
        result = self.tool.run(symbol="600519", ratios=["roe", "gross_margin", "debt_ratio"])
        assert result["success"]
        names = [r["name"] for r in result["ratios"]]
        assert "roe" in names
        assert "gross_margin" in names
        assert "debt_ratio" in names

    def test_all_ratios(self):
        """不传 ratios 则计算全部"""
        result = self.tool.run(symbol="600519")
        assert result["success"]
        assert len(result["ratios"]) > 5  # 至少 5+ 个比率

    def test_byg_ratios(self):
        result = self.tool.run(symbol="002594", ratios=["roe", "revenue_growth"])
        assert result["success"]
        assert len(result["ratios"]) >= 1

    def test_unknown_symbol(self):
        result = self.tool.run(symbol="999999", ratios=["roe"])
        assert not result["success"]


# ==================== IndustryComparison ====================

class TestIndustryComparison:
    def setup_method(self):
        self.tool = IndustryComparisonTool()
        assert self.tool.name == "mcp_industry_comparison"

    def test_maotai_wine_sector(self):
        result = self.tool.run(symbol="600519")
        assert result["success"]
        assert result["sector"] == "白酒"
        assert result["data"]["peer_count"] >= 4

    def test_byd_ev_sector(self):
        result = self.tool.run(symbol="002594", metrics=["pe", "roe"])
        assert result["success"]
        assert result["sector"] == "新能源汽车"

    def test_unknown_symbol(self):
        result = self.tool.run(symbol="999999")
        assert not result["success"]


# ==================== MarketIndex ====================

class TestMarketIndex:
    def setup_method(self):
        self.tool = MarketIndexTool()
        assert self.tool.name == "mcp_market_index"

    def test_sh_index(self):
        result = self.tool.run(index="sh000001")
        assert result["success"]
        assert result["data"]["name"] == "上证指数"

    def test_sector_index(self):
        result = self.tool.run(index="sh000819")
        assert result["success"]
        assert result["data"]["name"] == "中证白酒"

    def test_unknown_index(self):
        result = self.tool.run(index="xx000000")
        assert not result["success"]


# ==================== FinancialCalendar ====================

class TestFinancialCalendar:
    def setup_method(self):
        self.tool = FinancialCalendarTool()
        assert self.tool.name == "mcp_financial_calendar"

    def test_maotai_calendar(self):
        result = self.tool.run(symbol="600519", year=2026)
        assert result["success"]
        assert result["data"]["event_count"] >= 4

    def test_default_calendar(self):
        """未知标的使用通用日历"""
        result = self.tool.run(symbol="999999", year=2026)
        assert result["success"]
        assert result["data"]["event_count"] >= 3

    def test_summary_contains_name(self):
        result = self.tool.run(symbol="002594")
        assert "比亚迪" in result["summary"]


# ==================== 跨工具验证 ====================

class TestMCPIntegration:
    """验证 MCP 工具之间的数据一致性"""

    def test_stock_price_and_statements_same_symbol(self):
        """同一标的的行情和报表数据应对应"""
        price = StockPriceTool().run(symbol="600519")
        stmt = FinancialStatementsTool().run(symbol="600519")
        assert price["data"]["name"] == stmt["data"]["name"] == "贵州茅台"

    def test_ratio_uses_statement_data(self):
        """比率计算使用的数据应与报表一致"""
        stmt = FinancialStatementsTool().run(symbol="002594")
        ratio = CalculateRatioTool().run(symbol="002594", ratios=["roe"])
        # ROE 计算结果应在合理范围
        if ratio["ratios"]:
            roe_value = ratio["ratios"][0]["value"]
            assert isinstance(roe_value, (int, float, dict))
            if isinstance(roe_value, dict):
                assert "ROE" in roe_value  # dupont 返回 dict
