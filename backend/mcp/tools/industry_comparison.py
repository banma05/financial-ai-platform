"""
MCP 工具：行业对比分析

获取同行业可比公司的关键指标对比（PE/PB/ROE/营收增速等）。
"""
from typing import Dict, Any, List, Optional
from loguru import logger
from mcp import datasource


class IndustryComparisonTool:
    """行业对比工具"""

    def __init__(self):
        self.name = "mcp_industry_comparison"

    def run(
        self,
        symbol: str,
        metrics: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        获取同行业可比公司对比数据。

        参数:
            symbol: 标的代码（用于确定行业，如 600519→白酒行业）
            metrics: 对比指标，默认 pe/pb/roe/revenue_growth
        """
        logger.info(f"[IndustryComparison] {symbol}, metrics={metrics}")

        result = datasource.get_industry_comparison(symbol, metrics)
        if "error" in result:
            return {"success": False, "error": result["error"], "data": None}

        # 生成对比摘要
        peers = result.get("peers", [])
        sector = result["sector"]
        target = result.get("target", {})

        summary = f"{sector}行业共 {len(peers)} 家可比公司"
        if target:
            summary += f"，标的: {target.get('name', '')}"

        return {
            "success": True,
            "sector": sector,
            "data": result,
            "summary": summary,
        }
