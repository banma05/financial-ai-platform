"""
MCP 工具：财务报表查询

支持利润表/资产负债表/现金流量表，数据基于 2024 年年报。
返回结构与 data_query 兼容，可直接注入 executor 依赖注入。
"""
from typing import Dict, Any, Optional
from loguru import logger
from mcp import datasource


# 新浪 API 原始键名 → 标准中文键名（对齐 FINANCIAL_TERM_TO_PARAM）
_SINA_KEY_MAP = {
    "营业总收入": "营业收入", "营业收入": "营业收入",
    "营业总成本": "营业成本", "营业成本": "营业成本",
    "归属于母公司所有者的净利润": "净利润", "净利润": "净利润",
    "归属于母公司股东权益合计": "净资产", "股东权益合计": "净资产",
    "资产总计": "总资产", "负债合计": "总负债",
    "流动资产合计": "流动资产", "流动负债合计": "流动负债",
    "经营活动产生的现金流量净额": "经营现金流",
    "销售费用": "销售费用", "管理费用": "管理费用",
    "财务费用": "财务费用", "研发费用": "研发费用",
    "基本每股收益": "每股收益", "稀释每股收益": "每股收益",
    "少数股东权益": None,  # 跳过，防止误映射为 equity
    "其他权益工具": None, "永续债": None,
    "归属于母公司所有者的综合收益总额": None,
    "所有者权益合计": "净资产",
}


class FinancialStatementsTool:
    """财务报表查询工具 — V8.3 加键名归一化防止参数注入误配"""

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

        # 展平所有数据 + 键名归一化
        flat_data = {}
        for section_key in ("income", "balance", "cashflow"):
            section = result.get(section_key)
            if isinstance(section, dict):
                for raw_key, value in section.items():
                    mapped_key = _SINA_KEY_MAP.get(raw_key, raw_key)
                    if mapped_key is not None:  # None = 跳过（如少数股东权益）
                        flat_data[mapped_key] = value

        # data 也做归一化（供 executor 依赖注入读取）
        norm_data = {}
        for section_key in ("income", "balance", "cashflow"):
            section = result.get(section_key)
            if isinstance(section, dict):
                norm_section = {}
                for raw_key, value in section.items():
                    mapped_key = _SINA_KEY_MAP.get(raw_key, raw_key)
                    if mapped_key is not None:
                        norm_section[mapped_key] = value
                norm_data[section_key] = norm_section

        return {
            "success": True,
            "symbol": result["symbol"],
            "report_date": result.get("report_date", ""),
            "data": {**result, **norm_data, "flat_data": flat_data},
            "flat_data": flat_data,
            "summary": f"{result['name']}({result['symbol']}) {result.get('report_date', '')} 财务报表已获取",
        }
