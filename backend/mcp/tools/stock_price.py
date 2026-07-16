"""
MCP 工具：股票行情查询

支持实时行情 + 历史K线（日/周/月），Mock 数据覆盖 3 家核心标的。
"""
from typing import Dict, Any, Optional
from loguru import logger
from mcp import datasource


class StockPriceTool:
    """股票行情查询工具"""

    def __init__(self):
        self.name = "mcp_stock_price"

    def run(
        self,
        symbol: str,
        period: str = "realtime",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        查询股票行情。

        参数:
            symbol: 股票代码（600519 / 002594 / 00700）
            period: realtime / daily / weekly / monthly
        """
        logger.info(f"[StockPrice] 查询 {symbol}, period={period}")

        result = datasource.get_stock_price(symbol, period)
        if "error" in result:
            logger.warning(f"[StockPrice] {result['error']}")
            return {"success": False, "error": result["error"], "data": None}

        return {
            "success": True,
            "symbol": result["symbol"],
            "data": result,
            "summary": (f"{result['name']}({result['symbol']}) "
                        f"最新价 ¥{result['price']}，"
                        f"{'涨' if result['change'] >= 0 else '跌'}"
                        f"{abs(result['change_pct'])}%"),
        }
