"""
MCP Server — 独立进程部署（阶段四 Docker 化后启用）

当前阶段 MCP 工具通过 Agent 的 ToolRegistry 注册类运行在 Agent 进程中。
若要拆为独立进程，将后端/api/新增 mcp.py 路由代理到此处。

架构：
    Agent → ToolRegistry(MCPProxy) → HTTP → MCP Server(/tools/*)

当前此文件作架构预留，所有功能已在 backend/mcp/tools/ 中实现。
"""
from typing import Dict, Any


def run_tool(tool_name: str, **params) -> Dict[str, Any]:
    """通用工具调用入口（预留 HTTP 端点代理到此函数）"""
    from mcp import (
        StockPriceTool, FinancialStatementsTool, CalculateRatioTool,
        IndustryComparisonTool, MarketIndexTool, FinancialCalendarTool,
    )
    tools = {
        "stock_price": StockPriceTool(),
        "financial_statements": FinancialStatementsTool(),
        "calculate_ratio": CalculateRatioTool(),
        "industry_comparison": IndustryComparisonTool(),
        "market_index": MarketIndexTool(),
        "financial_calendar": FinancialCalendarTool(),
    }
    tool = tools.get(tool_name)
    if not tool:
        return {"success": False, "error": f"未知工具: {tool_name}"}
    return tool.run(**params)


if __name__ == "__main__":
    # 冒烟测试
    result = run_tool("stock_price", symbol="600519")
    print(f"stock_price(600519): success={result.get('success')}")
