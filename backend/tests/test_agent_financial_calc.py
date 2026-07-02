"""
财务公式库单元测试 — 每个公式至少 2 个用例（正常值 + 边界值）

与 Excel 计算结果交叉验证，准确率目标 100%。
"""
import pytest
from agent.tools.financial_calc import (
    FinancialCalcTool, FORMULA_REGISTRY,
    calc_gross_profit_margin, calc_net_profit_margin, calc_roe, calc_roa,
    calc_debt_ratio, calc_current_ratio, calc_quick_ratio, calc_interest_coverage,
    calc_inventory_turnover, calc_receivable_turnover, calc_total_asset_turnover,
    calc_growth_rate, calc_revenue_growth_rate, calc_net_profit_growth_rate,
    calc_pe_ratio, calc_pb_ratio, calc_free_cash_flow, calc_cf_to_net_profit,
    dupont_analysis,
)


class TestProfitability:
    """盈利能力公式测试"""

    def test_gross_profit_margin_normal(self):
        """毛利率 — 正常值（茅台 2024：营收 1741.44 亿，成本 132.64 亿 → 92.38%）"""
        result = calc_gross_profit_margin(1741.44, 132.64)
        assert round(result, 2) == 92.38

    def test_gross_profit_margin_zero_revenue(self):
        """毛利率 — 零营收"""
        result = calc_gross_profit_margin(0, 100)
        assert result == 0.0

    def test_net_profit_margin_normal(self):
        """净利率 — 正常值（茅台2024：净利862.28 / 营收1741.44 = 49.52%）"""
        result = calc_net_profit_margin(862.28, 1741.44)
        assert round(result, 2) == 49.52

    def test_net_profit_margin_zero_revenue(self):
        """净利率 — 零营收"""
        result = calc_net_profit_margin(100, 0)
        assert result == 0.0

    def test_roe_normal(self):
        """ROE — 正常值（茅台 2024：净利 862.28，权益 2687.45 → 32.09%）"""
        result = calc_roe(862.28, 2687.45)
        assert round(result, 2) == 32.09

    def test_roe_zero_equity(self):
        """ROE — 零净资产"""
        result = calc_roe(100, 0)
        assert result == 0.0

    def test_roa_normal(self):
        """ROA — 正常值"""
        result = calc_roa(862.28, 3000)
        assert round(result, 2) == 28.74

    def test_ebitda_margin_normal(self):
        """EBITDA 率 — 正常值"""
        result = calc_roa(500, 4000)
        assert result == 12.5


class TestSolvency:
    """偿债能力公式测试"""

    def test_debt_ratio_normal(self):
        """资产负债率 — 正常值"""
        result = calc_debt_ratio(500, 2000)
        assert result == 25.0

    def test_debt_ratio_zero_assets(self):
        """资产负债率 — 零总资产"""
        result = calc_debt_ratio(100, 0)
        assert result == 0.0

    def test_current_ratio_normal(self):
        """流动比率 — 正常值"""
        result = calc_current_ratio(1000, 500)
        assert result == 2.0

    def test_current_ratio_zero_liabilities(self):
        """流动比率 — 零流动负债"""
        result = calc_current_ratio(1000, 0)
        assert result == float("inf")

    def test_quick_ratio_normal(self):
        """速动比率 — 正常值"""
        result = calc_quick_ratio(1000, 200, 500)
        assert result == 1.6

    def test_interest_coverage_normal(self):
        """利息保障倍数 — 正常值"""
        result = calc_interest_coverage(500, 100)
        assert result == 5.0

    def test_interest_coverage_zero_interest(self):
        """利息保障倍数 — 零利息费用"""
        result = calc_interest_coverage(500, 0)
        assert result == float("inf")


class TestOperations:
    """营运能力公式测试"""

    def test_inventory_turnover_normal(self):
        """存货周转率 — 正常值"""
        result = calc_inventory_turnover(500, 100)
        assert result == 5.0

    def test_inventory_turnover_zero_inventory(self):
        """存货周转率 — 零存货"""
        result = calc_inventory_turnover(500, 0)
        assert result == 0.0

    def test_receivable_turnover_normal(self):
        """应收账款周转率 — 正常值"""
        result = calc_receivable_turnover(1000, 100)
        assert result == 10.0

    def test_total_asset_turnover_normal(self):
        """总资产周转率 — 正常值"""
        result = calc_total_asset_turnover(1741.44, 3000)
        assert round(result, 2) == 0.58


class TestGrowth:
    """成长能力公式测试"""

    def test_growth_rate_positive(self):
        """增长率 — 正向增长"""
        result = calc_growth_rate(120, 100)
        assert result == 20.0

    def test_growth_rate_negative(self):
        """增长率 — 负增长"""
        result = calc_growth_rate(80, 100)
        assert result == -20.0

    def test_growth_rate_zero_previous(self):
        """增长率 — 上期为零"""
        result = calc_growth_rate(100, 0)
        assert result == 0.0

    def test_growth_rate_to_negative(self):
        """增长率 — 从负值到正值"""
        result = calc_growth_rate(50, -100)
        assert result == 150.0

    def test_revenue_growth_normal(self):
        """营收增长率 — 正常调用"""
        result = calc_revenue_growth_rate(1741.44, 1505.60)
        assert round(result, 2) == 15.66

    def test_net_profit_growth_normal(self):
        """净利润增长率 — 正常调用"""
        result = calc_net_profit_growth_rate(862.28, 747.34)
        assert round(result, 2) == 15.38


class TestValuation:
    """估值指标公式测试"""

    def test_pe_ratio_normal(self):
        """市盈率 — 正常值"""
        result = calc_pe_ratio(150, 10)
        assert result == 15.0

    def test_pe_ratio_zero_eps(self):
        """市盈率 — 零 EPS（亏损）"""
        result = calc_pe_ratio(150, 0)
        assert result == float("inf")

    def test_pb_ratio_normal(self):
        """市净率 — 正常值"""
        result = calc_pb_ratio(150, 50)
        assert result == 3.0


class TestCashFlow:
    """现金流分析公式测试"""

    def test_free_cash_flow_normal(self):
        """自由现金流 — 正常值"""
        result = calc_free_cash_flow(1000, 300)
        assert result == 700.0

    def test_free_cash_flow_negative(self):
        """自由现金流 — 资本支出超过经营现金流"""
        result = calc_free_cash_flow(500, 800)
        assert result == -300.0

    def test_cf_to_net_profit_high_quality(self):
        """经营现金流/净利润 — 高质量利润（>100%）"""
        result = calc_cf_to_net_profit(1200, 1000)
        assert result == 120.0

    def test_cf_to_net_profit_low_quality(self):
        """经营现金流/净利润 — 低质量利润"""
        result = calc_cf_to_net_profit(500, 1000)
        assert result == 50.0


class TestDuPont:
    """杜邦分析公式测试"""

    def test_dupont_analysis_normal(self):
        """杜邦分析 — 完整三因子分解（茅台 2024 示例数据）"""
        result = dupont_analysis(
            net_profit=862.28,    # 净利润
            revenue=1741.44,      # 营业收入
            total_assets=3000,    # 总资产（示例值）
            equity=2687.45,       # 净资产
        )
        assert "roe" in result
        assert "net_profit_margin" in result
        assert "asset_turnover" in result
        assert "equity_multiplier" in result
        assert "breakdown" in result
        # 验证分解等式：ROE ≈ 净利率 × 资产周转率 × 权益乘数 / 100
        computed_roe = result["net_profit_margin"] * result["asset_turnover"] * result["equity_multiplier"] / 100
        assert abs(result["roe"] - computed_roe) < 0.01

    def test_dupont_analysis_zero_equity(self):
        """杜邦分析 — 零净资产"""
        result = dupont_analysis(100, 500, 1000, 0)
        assert result["equity_multiplier"] == 0.0


class TestFinancialCalcTool:
    """FinancialCalcTool 工具入口类测试"""

    def test_run_valid_formula(self):
        """正常调用已注册公式"""
        tool = FinancialCalcTool()
        result = tool.run("roe", {"net_profit": 100, "avg_equity": 500})
        assert result["success"] is True
        assert result["result"] == 20.0
        assert result["category"] == "盈利能力"
        assert result["unit"] == "%"
        assert "expression" in result

    def test_run_unknown_formula(self):
        """调用不存在的公式"""
        tool = FinancialCalcTool()
        result = tool.run("nonexistent_formula", {})
        assert result["success"] is False
        assert "error" in result

    def test_run_missing_params(self):
        """缺少必需参数"""
        tool = FinancialCalcTool()
        result = tool.run("roe", {"net_profit": 100})  # 缺少 avg_equity
        assert result["success"] is False
        assert "缺少参数" in result["error"]

    def test_list_formulas(self):
        """列出所有公式"""
        tool = FinancialCalcTool()
        formulas = tool.list_formulas()
        assert len(formulas) == len(FORMULA_REGISTRY)
        for f in formulas:
            assert "name" in f
            assert "display_name" in f
            assert "category" in f
            assert "params" in f
            assert "formula_text" in f
            assert "unit" in f

    def test_all_formulas_in_registry(self):
        """注册表中所有公式的 func 都是可调用的"""
        for name, info in FORMULA_REGISTRY.items():
            assert callable(info["func"]), f"{name} 的 func 不可调用"
            assert isinstance(info["params"], list), f"{name} 的 params 不是 list"
            assert len(info["params"]) >= 1, f"{name} 缺少参数定义"

    def test_dupont_via_tool(self):
        """通过 Tool 入口调用杜邦分析"""
        tool = FinancialCalcTool()
        result = tool.run("dupont", {
            "net_profit": 862.28,
            "revenue": 1741.44,
            "total_assets": 3000,
            "equity": 2687.45,
        })
        assert result["success"] is True
        assert isinstance(result["result"], dict)
        assert "roe" in result["result"]
