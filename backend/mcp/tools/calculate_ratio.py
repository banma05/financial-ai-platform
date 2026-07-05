"""
MCP 工具：财务比率批量计算

复用模块二的 financial_calc 公式库（不重复造轮子），
先从 Mock 取财务报表数据，再套 19 个公式计算。

支持的比率（15个）：
    盈利能力: roe, roa, gross_margin, net_margin
    偿债能力: debt_ratio, current_ratio, quick_ratio, interest_coverage
    营运能力: inventory_turnover, receivable_turnover, total_asset_turnover
    成长能力: revenue_growth, net_profit_growth
    估值指标: pe_ratio, pb_ratio
    现金流: fcf, cf_to_net_profit
    杜邦分析: dupont
"""
from typing import Dict, Any, List, Optional
from loguru import logger
from agent.tools.financial_calc import FORMULA_REGISTRY
from mcp import mock_data


class CalculateRatioTool:
    """财务比率批量计算工具"""

    def __init__(self):
        self.name = "mcp_calculate_ratio"

    # 比率映射：用户输入 → 公式注册表键名
    RATIO_MAP = {
        "roe": "roe", "roa": "roa",
        "gross_margin": "gross_profit_margin", "net_margin": "net_profit_margin",
        "debt_ratio": "debt_ratio", "current_ratio": "current_ratio",
        "quick_ratio": "quick_ratio", "interest_coverage": "interest_coverage",
        "inventory_turnover": "inventory_turnover",
        "receivable_turnover": "receivable_turnover",
        "total_asset_turnover": "total_asset_turnover",
        "revenue_growth": "revenue_growth_rate",
        "net_profit_growth": "net_profit_growth_rate",
        "pe_ratio": "pe_ratio", "pb_ratio": "pb_ratio",
        "fcf": "free_cash_flow", "cf_to_net_profit": "cf_to_net_profit",
        "dupont": "dupont",
    }

    # 参数名映射：财务数据键名 → 公式参数名
    PARAM_MAP = {
        "营业收入": "revenue", "营业成本": "cost",
        "净利润": "net_profit",
        "总资产": "total_assets", "总负债": "total_liabilities",
        "净资产": "equity",
        "流动资产": "current_assets", "流动负债": "current_liabilities",
        "存货": "inventory",
        "财务费用": "interest_expense",
        "经营活动现金流净额": "operating_cf",
        "投资活动现金流净额": "investing_cf",
        "资本支出": "capital_expenditure",
        "基本每股收益": "eps", "股价": "stock_price",
    }

    def run(
        self,
        symbol: str,
        ratios: Optional[List[str]] = None,
        year: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        批量计算财务比率。

        参数:
            symbol: 股票代码
            ratios: 要计算的比率列表，不传则计算全部 15 个
            year: 年份（暂未使用，始终用最新 Mock 数据）
        """
        logger.info(f"[CalculateRatio] {symbol}, ratios={ratios}")

        # 1. 获取财务报表数据
        stmt = mock_data.get_financial_statements(symbol, "all")
        if "error" in stmt:
            return {"success": False, "error": stmt["error"], "data": None}

        # 2. 获取股价（PE/PB 需要）
        price_data = mock_data.get_stock_price(symbol)

        # 3. 组装公式参数
        params = self._assemble_params(stmt, price_data)

        # 4. 确定要计算的比率
        if ratios is None:
            ratios = list(self.RATIO_MAP.keys())
        else:
            # 过滤不支持的比率
            ratios = [r for r in ratios if r in self.RATIO_MAP]

        # 5. 逐个计算
        results = []
        for ratio_key in ratios:
            formula_key = self.RATIO_MAP[ratio_key]
            formula_info = FORMULA_REGISTRY.get(formula_key)
            if not formula_info:
                continue

            func = formula_info["func"]
            param_names = formula_info["params"]
            display_name = formula_info["display_name"]
            formula_text = formula_info["formula_text"]
            unit = formula_info.get("unit", "%")

            # 提取参数
            args = []
            missing = []
            for pname in param_names:
                if pname in params:
                    args.append(params[pname])
                else:
                    missing.append(pname)

            if missing:
                logger.debug(f"  {ratio_key}: 缺参数 {missing}，跳过")
                continue

            # 调用公式函数
            try:
                if formula_key == "dupont":
                    value = func(*args)
                    # 杜邦返回 dict
                    results.append({
                        "name": ratio_key, "display_name": display_name,
                        "value": value,
                        "unit": unit, "formula": formula_text,
                        "interpretation": _interpret_dupont(value),
                    })
                else:
                    value = func(*args)
                    results.append({
                        "name": ratio_key, "display_name": display_name,
                        "value": value,
                        "unit": unit, "formula": formula_text,
                        "interpretation": _interpret_ratio(ratio_key, value, unit),
                    })
            except Exception as e:
                logger.warning(f"  {ratio_key}: 计算失败 {e}")
                continue

        logger.info(f"[CalculateRatio] 完成: {len(results)}/{len(ratios)} 个比率")
        return {
            "success": True,
            "symbol": stmt["symbol"],
            "name": stmt["name"],
            "ratios": results,
            "summary": f"{stmt['name']} 共计算 {len(results)} 个财务比率",
        }

    def _assemble_params(
        self,
        stmt: Dict[str, Any],
        price_data: Dict[str, Any],
    ) -> Dict[str, float]:
        """从财务报表和行情数据组装公式参数"""
        params = {}

        # 展开财务报表数据
        for section_key in ("income", "balance", "cashflow"):
            section = stmt.get(section_key)
            if isinstance(section, dict):
                for k, v in section.items():
                    mapped_key = self.PARAM_MAP.get(k, k)
                    if isinstance(v, (int, float)):
                        params[mapped_key] = float(v)

        # 添加股价和 EPS
        if "price" in price_data:
            params["stock_price"] = float(price_data["price"])
        if "pe_ttm" in price_data and params.get("stock_price") and params.get("net_profit"):
            # 从 PE 反推 EPS（简化：PE=价格/EPS）
            pass  # EPS 已在报表中

        # 衍生参数
        if "net_profit" in params and "equity" in params:
            params["avg_equity"] = params["equity"]  # 简化：直接用期末值
        if "net_profit" in params and "revenue" in params:
            # 往期数据已在报表中
            pass

        return params


def _interpret_ratio(key: str, value: float, unit: str) -> str:
    """根据比率值给出简要解读"""
    if key == "roe":
        return "优秀(>20%)" if value > 20 else ("良好(10-20%)" if value > 10 else "偏低(<10%)")
    if key == "debt_ratio":
        return "低杠杆" if value < 40 else ("适中" if value < 60 else "高杠杆")
    if key == "current_ratio":
        return "流动性充足" if value > 2 else ("流动性正常" if value > 1 else "流动性偏紧")
    if key == "revenue_growth":
        return "高增长" if value > 20 else ("稳健增长" if value > 10 else ("增速放缓" if value > 0 else "负增长"))
    if key == "gross_margin":
        return "极高毛利" if value > 60 else ("高毛利" if value > 30 else "毛利偏低")
    return ""


def _interpret_dupont(value: Dict[str, Any]) -> str:
    """杜邦分析解读"""
    roe = value.get("ROE", 0)
    return "优秀(>20%)" if roe > 20 else ("良好(10-20%)" if roe > 10 else "偏低(<10%)")
