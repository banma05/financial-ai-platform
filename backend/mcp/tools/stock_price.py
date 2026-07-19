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

    @staticmethod
    def _resolve(symbol: str) -> str:
        """将公司名自动转为股票代码（如 "比亚迪" → "002594"）"""
        if not symbol:
            return symbol
        # 已经是纯数字代码，直接返回
        clean = symbol.replace(".SH", "").replace(".SZ", "").replace(".HK", "")
        if clean.isdigit():
            return clean
        # 公司名 → 代码映射
        name_to_code = {
            "贵州茅台": "600519", "茅台": "600519",
            "比亚迪": "002594",
            "宁德时代": "300750", "宁德": "300750",
            "五粮液": "000858",
            "招商银行": "600036", "招行": "600036",
            "腾讯控股": "00700", "腾讯": "00700",
            "美的集团": "000333", "美的": "000333",
            "格力电器": "000651", "格力": "000651",
            "隆基绿能": "601012", "隆基": "601012",
            "中国平安": "601318", "平安": "601318",
            "恒瑞医药": "600276", "恒瑞": "600276",
            "伊利股份": "600887", "伊利": "600887",
        }
        for name, code in name_to_code.items():
            if name in symbol or symbol in name:
                return code
        return symbol

    def run(
        self,
        symbol: str,
        period: str = "realtime",
        target_date: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        查询股票行情。

        参数:
            symbol: 股票代码（600519 / 002594 / 00700）或公司名（贵州茅台 / 比亚迪 / 腾讯控股）
            period: realtime / daily / weekly / monthly
            target_date: 目标日期 YYYY-MM-DD（用于查历史年末收盘价），为空则取实时价
        """
        # 自动将公司名转为股票代码（防止 LLM 传入"比亚迪"等名称）
        symbol = self._resolve(symbol)
        logger.info(f"[StockPrice] 查询 {symbol}, period={period}, target_date={target_date or '实时'}")

        result = datasource.get_stock_price(symbol, period, target_date=target_date)
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
