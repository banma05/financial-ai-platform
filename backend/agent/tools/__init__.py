"""
Agent 工具包 — 为 Agent 提供"手"的能力

工具类型：
- DataQueryTool: 从知识库检索结构化财务数据
- FinancialCalcTool: 15+ 内置财务公式
- ChartTool: matplotlib 图表生成
"""

# 🔧 懒加载：避免 import agent.tools 时触发 RAG/matplotlib 依赖
# 直接导入无需外部依赖的子模块
from .financial_calc import FinancialCalcTool, FORMULA_REGISTRY


def __getattr__(name):
    if name == "DataQueryTool":
        from .data_query import DataQueryTool
        return DataQueryTool
    if name == "ChartTool":
        from .chart import ChartTool
        return ChartTool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DataQueryTool",
    "FinancialCalcTool",
    "FORMULA_REGISTRY",
    "ChartTool",
]
