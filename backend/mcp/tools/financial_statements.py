"""
MCP 工具：财务报表查询

支持利润表/资产负债表/现金流量表，数据基于 2024 年年报。
返回结构与 data_query 兼容，可直接注入 executor 依赖注入。
"""
from typing import Dict, Any, Optional
from loguru import logger
from mcp import datasource


class FinancialStatementsTool:
    """财务报表查询工具"""

    def __init__(self):
        self.name = "mcp_financial_statements"

    def run(
        self,
        symbol: str,
        statement_type: str = "all",
        period: str = "annual",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        获取财务报表。

        参数:
            symbol: 股票代码
            statement_type: income(利润表) / balance(资产负债表) / cashflow(现金流) / all(全部)
            period: annual / quarterly
        """
        logger.info(f"[FinancialStatements] {symbol}, type={statement_type}")

        result = datasource.get_financial_statements(symbol, statement_type, period)
        if "error" in result:
            return {"success": False, "error": result["error"], "data": None}

        # 展平所有数据到顶层（兼容 executor 的依赖注入）
        flat_data = {}
        for section_key in ("income", "balance", "cashflow"):
            section = result.get(section_key)
            if isinstance(section, dict):
                flat_data.update(section)

        return {
            "success": True,
            "symbol": result["symbol"],
            "report_date": result.get("report_date", ""),
            "data": result,
            "flat_data": flat_data,  # 已展平，直接可用于公式计算
            "summary": f"{result['name']}({result['symbol']}) {result.get('report_date', '')} 财务报表已获取",
        }
