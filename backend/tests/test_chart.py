"""图表工具测试 — V9.1: None 数据防御

回归: V9-F15 伊利股份 ROE 杜邦雷达图, values 含 None 时
recommend 的 all(v>0) / abs(v) 抛 "'>' not supported between
'NoneType' and 'float'", 导致整个 Agent 执行失败。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.tools.chart import ChartTool


class TestChartNoneDefense:
    """V9.1: values 含 None 时不崩溃"""

    def test_values_with_none_cleaned(self):
        """含 None 的 values 被清洗, 仍能生成图表"""
        tool = ChartTool()
        r = tool.run(chart_type="auto", title="杜邦分解", data={
            "labels": ["净利率", "总资产周转率", "权益乘数"],
            "values": [16.5, None, 2.3],
        })
        assert not r.get("skip"), "含有效数据不应 skip"
        assert r.get("chart_option") or r.get("chart_options")

    def test_all_none_returns_empty_data(self):
        """全部为 None → 走 empty_data 防线, 不崩溃"""
        tool = ChartTool()
        r = tool.run(chart_type="auto", title="测试", data={
            "labels": ["a", "b"],
            "values": [None, None],
        })
        assert r.get("skip") is True
        assert r.get("skip_reason") == "empty_data"

    def test_normal_values_unchanged(self):
        """正常数据不受清洗逻辑影响"""
        tool = ChartTool()
        r = tool.run(chart_type="auto", title="正常", data={
            "labels": ["毛利率", "净利率"],
            "values": [91.18, 48.76],
        })
        assert r.get("chart_option") or r.get("chart_options")


class TestChartRecommendation:
    """图表自动选型 — V9.1: 正负混杂降级柱状图"""

    def test_positive_negative_uses_bar(self):
        """现金流正负混杂（流入/流出）→ 柱状图, 雷达图不适合负数"""
        tool = ChartTool()
        r = tool.recommend({
            "labels": ["经营现金流", "投资现金流", "筹资现金流", "资本支出"],
            "values": [133453873000, -129082282000, -10267547000, 14448245500],
        })
        assert r["chart_type"] == "bar"

    def test_all_positive_multi_dim_keeps_radar(self):
        """全正多指标（打分维度）→ 保持雷达图"""
        tool = ChartTool()
        r = tool.recommend({
            "labels": ["毛利率", "净利率", "ROE", "ROA"],
            "values": [91.18, 48.76, 33.65, 28.9],
        })
        assert r["chart_type"] == "radar"

    def test_amount_metrics_uses_bar(self):
        """金额类指标（营收/成本/净利）→ 柱状图, 不被量纲差异误导成雷达"""
        tool = ChartTool()
        r = tool.recommend({
            "labels": ["营业收入", "营业成本", "净利润"],
            "values": [1688, 148, 823],
        })
        assert r["chart_type"] == "bar"

    def test_amount_metrics_multi_company_uses_bar(self):
        """跨公司金额对比（茅台/五粮液/洋河营收）→ 柱状图"""
        tool = ChartTool()
        r = tool.recommend({
            "labels": ["茅台营收", "五粮液营收", "洋河营收"],
            "values": [1688, 832, 331],
        })
        assert r["chart_type"] == "bar"

    def test_time_series_uses_line(self):
        """多年趋势（营收_2022..2024）→ 折线图"""
        tool = ChartTool()
        r = tool.recommend({
            "labels": ["营业收入_2022", "营业收入_2023", "营业收入_2024"],
            "values": [1241, 1477, 1688],
        })
        assert r["chart_type"] == "line"

    def test_time_series_not_pie_when_sum_100(self):
        """多年趋势 sum≈100 不误判饼图（ROE 三年趋势回归）"""
        tool = ChartTool()
        r = tool.recommend({
            "labels": ["ROE_2022", "ROE_2023", "ROE_2024"],
            "values": [28.9, 31.2, 33.65],
        })
        assert r["chart_type"] == "line"

    def test_ratio_assessment_uses_radar(self):
        """比率类评估维度（杜邦分解三因子）→ 雷达图"""
        tool = ChartTool()
        r = tool.recommend({
            "labels": ["净利率", "总资产周转率", "权益乘数"],
            "values": [48.76, 0.55, 2.4],
        })
        assert r["chart_type"] == "radar"
