"""
MCP 模块 — 外部金融数据源接入（阶段三）

提供 6 个工具：
- StockPriceTool:         股票实时行情/历史K线
- FinancialStatementsTool: 财务报表（利润表/资产负债表/现金流）
- CalculateRatioTool:      财务比率批量计算（复用 financial_calc）
- IndustryComparisonTool:  同行业可比公司对比
- MarketIndexTool:         大盘/行业指数行情
- FinancialCalendarTool:   财报日历（披露日/分红/股东大会）

所有工具实现统一协议：.name 属性 + .run(**params) 方法。
通过 Agent 的 ToolRegistry.register() 透明接入 LangGraph 编排。
"""

from .tools.stock_price import StockPriceTool
from .tools.financial_statements import FinancialStatementsTool
from .tools.calculate_ratio import CalculateRatioTool
from .tools.industry_comparison import IndustryComparisonTool
from .tools.market_index import MarketIndexTool
from .tools.financial_calendar import FinancialCalendarTool

__all__ = [
    "StockPriceTool",
    "FinancialStatementsTool",
    "CalculateRatioTool",
    "IndustryComparisonTool",
    "MarketIndexTool",
    "FinancialCalendarTool",
]
