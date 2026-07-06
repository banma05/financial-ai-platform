"""
Agent 工具包 — 为 Agent 提供"手"的能力

工具类型：
- FinancialCalcTool: 15+ 内置财务公式（即时导入，无外部重依赖）
- DataQueryTool:   知识库检索（惰性导入，避免触发 RAG 全链路）
- ChartTool:       matplotlib 图表生成（惰性导入，避免触发 matplotlib）
"""
from .financial_calc import FinancialCalcTool, FORMULA_REGISTRY


def __getattr__(name):
    """惰性加载 DataQueryTool / ChartTool（避免 RAG / matplotlib 重依赖）"""
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
