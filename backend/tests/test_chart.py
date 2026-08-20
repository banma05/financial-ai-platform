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
