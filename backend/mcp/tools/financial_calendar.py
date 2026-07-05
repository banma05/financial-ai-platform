"""
MCP 工具：财报日历

查询上市公司的财报披露、分红除权、股东大会等重要日期。
"""
from typing import Dict, Any
from loguru import logger
from mcp import mock_data


class FinancialCalendarTool:
    """财报日历查询工具"""

    def __init__(self):
        self.name = "mcp_financial_calendar"

    def run(
        self,
        symbol: str,
        year: int = 2026,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        查询财报日历。

        参数:
            symbol: 股票代码
            year: 年份
        """
        logger.info(f"[FinancialCalendar] {symbol}, {year}")

        result = mock_data.get_financial_calendar(symbol, year)
        if "error" in result:
            return {"success": False, "error": result["error"], "data": None}

        events = result.get("events", [])
        next_events = [e for e in events if e["date"] >= "2026-07-05"][:3]

        return {
            "success": True,
            "data": result,
            "summary": (f"{result['name']} {year}年共 {len(events)} 个重要日期"
                        + (f"，近期: {next_events[0]['description']}" if next_events else "")),
        }
