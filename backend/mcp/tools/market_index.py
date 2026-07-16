"""
MCP 工具：市场指数行情

支持上证/沪深300/深证/创业板/行业指数查询。
"""
from typing import Dict, Any
from loguru import logger
from mcp import datasource


class MarketIndexTool:
    """市场指数查询工具"""

    def __init__(self):
        self.name = "mcp_market_index"

    def run(
        self,
        index: str = "sh000001",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        查询市场指数行情。

        参数:
            index: 指数代码
                sh000001 — 上证指数
                sh000300 — 沪深300
                sz399001 — 深证成指
                sz399006 — 创业板指
                sh000819 — 中证白酒
                sh931079 — 新能源车
        """
        logger.info(f"[MarketIndex] {index}")

        result = datasource.get_market_index(index)
        if "error" in result:
            return {"success": False, "error": result["error"], "data": None}

        return {
            "success": True,
            "data": result,
            "summary": (f"{result['name']}({result['code']}) "
                        f"{result['price']}，"
                        f"{'涨' if result['change'] >= 0 else '跌'}"
                        f"{abs(result['change_pct'])}%"),
        }
