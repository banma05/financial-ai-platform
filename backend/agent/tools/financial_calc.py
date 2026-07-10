"""
内置财务公式库 — 纯 Python 实现，零外部依赖

覆盖 BRD 规划的 7 大类、20+ 公式：
- 盈利能力 5 个
- 偿债能力 4 个
- 营运能力 3 个
- 成长能力 3 个
- 估值指标 2 个（基础版）
- 现金流 2 个
- 杜邦分析 1 个

所有公式与 Excel 计算结果交叉验证，准确率目标 100%。
"""
from typing import List, Dict, Any, Optional


# ==================== 盈利能力 ====================

def calc_gross_profit_margin(revenue: float, cost: float) -> float:
    """
    毛利率 = (营业收入 - 营业成本) / 营业收入 × 100%

    参数:
        revenue: 营业收入
        cost: 营业成本
    """
    if revenue == 0:
        return 0.0
    return round((revenue - cost) / revenue * 100, 2)


def calc_net_profit_margin(net_profit: float, revenue: float) -> float:
    """
    净利率 = 净利润 / 营业收入 × 100%
    """
    if revenue == 0:
        return 0.0
    return round(net_profit / revenue * 100, 2)


def calc_roe(net_profit: float, avg_equity: float) -> float:
    """
    ROE（净资产收益率）= 净利润 / 平均净资产 × 100%

    平均净资产 = (期初净资产 + 期末净资产) / 2
    如果已有平均值，直接传入 avg_equity
    """
    if avg_equity == 0:
        return 0.0
    return round(net_profit / avg_equity * 100, 2)


def calc_roa(net_profit: float, avg_total_assets: float) -> float:
    """
    ROA（总资产收益率）= 净利润 / 平均总资产 × 100%
    """
    if avg_total_assets == 0:
        return 0.0
    return round(net_profit / avg_total_assets * 100, 2)


def calc_ebitda_margin(ebitda: float, revenue: float) -> float:
    """
    EBITDA 率 = EBITDA / 营业收入 × 100%
    """
    if revenue == 0:
        return 0.0
    return round(ebitda / revenue * 100, 2)


# ==================== 偿债能力 ====================

def calc_debt_ratio(total_liabilities: float, total_assets: float) -> float:
    """
    资产负债率 = 总负债 / 总资产 × 100%
    """
    if total_assets == 0:
        return 0.0
    return round(total_liabilities / total_assets * 100, 2)


def calc_current_ratio(current_assets: float, current_liabilities: float) -> float:
    """
    流动比率 = 流动资产 / 流动负债
    """
    if current_liabilities == 0:
        return float("inf")
    return round(current_assets / current_liabilities, 2)


def calc_quick_ratio(
    current_assets: float, inventory: float, current_liabilities: float
) -> float:
    """
    速动比率 = (流动资产 - 存货) / 流动负债
    """
    if current_liabilities == 0:
        return float("inf")
    return round((current_assets - inventory) / current_liabilities, 2)


def calc_interest_coverage(ebit: float, interest_expense: float) -> float:
    """
    利息保障倍数 = EBIT / 利息费用
    """
    if interest_expense == 0:
        return float("inf")
    return round(ebit / interest_expense, 2)


# ==================== 营运能力 ====================

def calc_inventory_turnover(cost: float, avg_inventory: float) -> float:
    """
    存货周转率（次）= 营业成本 / 平均存货
    """
    if avg_inventory == 0:
        return 0.0
    return round(cost / avg_inventory, 2)


def calc_receivable_turnover(revenue: float, avg_receivables: float) -> float:
    """
    应收账款周转率（次）= 营业收入 / 平均应收账款
    """
    if avg_receivables == 0:
        return 0.0
    return round(revenue / avg_receivables, 2)


def calc_total_asset_turnover(revenue: float, avg_total_assets: float) -> float:
    """
    总资产周转率（次）= 营业收入 / 平均总资产
    """
    if avg_total_assets == 0:
        return 0.0
    return round(revenue / avg_total_assets, 2)


# ==================== 成长能力 ====================

def calc_growth_rate(current: float, previous: float) -> float:
    """
    通用增长率 = (当期值 - 上期值) / |上期值| × 100%

    使用绝对值分母避免负数上期时的符号错误
    """
    if previous == 0:
        return 0.0
    return round((current - previous) / abs(previous) * 100, 2)


def calc_revenue_growth_rate(current_revenue: float, previous_revenue: float) -> float:
    """营收增长率"""
    return calc_growth_rate(current_revenue, previous_revenue)


def calc_net_profit_growth_rate(current_profit: float, previous_profit: float) -> float:
    """净利润增长率"""
    return calc_growth_rate(current_profit, previous_profit)


# ==================== 估值指标（基础版）====================

def calc_pe_ratio(stock_price: float, eps: float) -> float:
    """
    市盈率 PE = 股价 / 每股收益
    """
    if eps == 0:
        return float("inf")
    return round(stock_price / eps, 2)


def calc_pb_ratio(stock_price: float, bvps: float) -> float:
    """
    市净率 PB = 股价 / 每股净资产
    """
    if bvps == 0:
        return float("inf")
    return round(stock_price / bvps, 2)


# ==================== 现金流分析 ====================

def calc_free_cash_flow(operating_cf: float, capital_expenditure: float) -> float:
    """
    自由现金流 FCF = 经营活动现金流净额 - 资本支出
    """
    return round(operating_cf - capital_expenditure, 2)


def calc_cf_to_net_profit(operating_cf: float, net_profit: float) -> float:
    """
    经营现金流 / 净利润比率

    该比率 > 1 说明利润质量高（有真金白银支撑）
    该比率 < 1 说明利润可能含较多应收款等非现金项目
    """
    if net_profit == 0:
        return 0.0
    return round(operating_cf / net_profit * 100, 2)


# ==================== 杜邦分析 ====================

def dupont_analysis(
    net_profit: float, revenue: float, total_assets: float, equity: float
) -> dict:
    """
    杜邦分析：ROE 三因子分解

    ROE = 净利率 × 总资产周转率 × 权益乘数

    权益乘数 = 总资产 / 净资产

    返回:
        {
            "roe": float,                  # 净资产收益率 (%)
            "net_profit_margin": float,    # 净利率 (%)
            "asset_turnover": float,       # 总资产周转率 (次)
            "equity_multiplier": float,    # 权益乘数
            "breakdown": str,              # 中文分解表达式
        }
    """
    npm = calc_net_profit_margin(net_profit, revenue)
    at = calc_total_asset_turnover(revenue, total_assets)
    em = round(total_assets / equity, 2) if equity != 0 else 0.0
    roe = round(npm * at * em / 100, 2)  # npm 和 at 是百分数

    return {
        "roe": roe,
        "net_profit_margin": npm,
        "asset_turnover": at,
        "equity_multiplier": em,
        "breakdown": f"ROE({roe}%) = 净利率({npm}%) × 资产周转率({at}次) × 权益乘数({em})",
    }


# ==================== 公式注册表 ====================

FORMULA_REGISTRY: Dict[str, dict] = {
    # 盈利能力
    "gross_profit_margin": {
        "func": calc_gross_profit_margin,
        "params": ["revenue", "cost"],
        "category": "盈利能力",
        "display_name": "毛利率",
        "formula_text": "毛利率 = (营业收入 - 营业成本) / 营业收入 × 100%",
        "unit": "%",
    },
    "net_profit_margin": {
        "func": calc_net_profit_margin,
        "params": ["net_profit", "revenue"],
        "category": "盈利能力",
        "display_name": "净利率",
        "formula_text": "净利率 = 净利润 / 营业收入 × 100%",
        "unit": "%",
    },
    "roe": {
        "func": calc_roe,
        "params": ["net_profit", "avg_equity"],
        "category": "盈利能力",
        "display_name": "ROE（净资产收益率）",
        "formula_text": "ROE = 净利润 / 平均净资产 × 100%",
        "unit": "%",
    },
    "roa": {
        "func": calc_roa,
        "params": ["net_profit", "avg_total_assets"],
        "category": "盈利能力",
        "display_name": "ROA（总资产收益率）",
        "formula_text": "ROA = 净利润 / 平均总资产 × 100%",
        "unit": "%",
    },
    "ebitda_margin": {
        "func": calc_ebitda_margin,
        "params": ["ebitda", "revenue"],
        "category": "盈利能力",
        "display_name": "EBITDA 率",
        "formula_text": "EBITDA 率 = EBITDA / 营业收入 × 100%",
        "unit": "%",
    },
    # 偿债能力
    "debt_ratio": {
        "func": calc_debt_ratio,
        "params": ["total_liabilities", "total_assets"],
        "category": "偿债能力",
        "display_name": "资产负债率",
        "formula_text": "资产负债率 = 总负债 / 总资产 × 100%",
        "unit": "%",
    },
    "current_ratio": {
        "func": calc_current_ratio,
        "params": ["current_assets", "current_liabilities"],
        "category": "偿债能力",
        "display_name": "流动比率",
        "formula_text": "流动比率 = 流动资产 / 流动负债",
        "unit": "倍",
    },
    "quick_ratio": {
        "func": calc_quick_ratio,
        "params": ["current_assets", "inventory", "current_liabilities"],
        "category": "偿债能力",
        "display_name": "速动比率",
        "formula_text": "速动比率 = (流动资产 - 存货) / 流动负债",
        "unit": "倍",
    },
    "interest_coverage": {
        "func": calc_interest_coverage,
        "params": ["ebit", "interest_expense"],
        "category": "偿债能力",
        "display_name": "利息保障倍数",
        "formula_text": "利息保障倍数 = EBIT / 利息费用",
        "unit": "倍",
    },
    # 营运能力
    "inventory_turnover": {
        "func": calc_inventory_turnover,
        "params": ["cost", "avg_inventory"],
        "category": "营运能力",
        "display_name": "存货周转率",
        "formula_text": "存货周转率 = 营业成本 / 平均存货",
        "unit": "次",
    },
    "receivable_turnover": {
        "func": calc_receivable_turnover,
        "params": ["revenue", "avg_receivables"],
        "category": "营运能力",
        "display_name": "应收账款周转率",
        "formula_text": "应收账款周转率 = 营业收入 / 平均应收账款",
        "unit": "次",
    },
    "total_asset_turnover": {
        "func": calc_total_asset_turnover,
        "params": ["revenue", "avg_total_assets"],
        "category": "营运能力",
        "display_name": "总资产周转率",
        "formula_text": "总资产周转率 = 营业收入 / 平均总资产",
        "unit": "次",
    },
    # 成长能力
    "revenue_growth": {
        "func": calc_revenue_growth_rate,
        "params": ["current_revenue", "previous_revenue"],
        "category": "成长能力",
        "display_name": "营收增长率",
        "formula_text": "营收增长率 = (当期营收 - 上期营收) / |上期营收| × 100%",
        "unit": "%",
    },
    "net_profit_growth": {
        "func": calc_net_profit_growth_rate,
        "params": ["current_profit", "previous_profit"],
        "category": "成长能力",
        "display_name": "净利润增长率",
        "formula_text": "净利润增长率 = (当期净利 - 上期净利) / |上期净利| × 100%",
        "unit": "%",
    },
    # 估值指标
    "pe_ratio": {
        "func": calc_pe_ratio,
        "params": ["stock_price", "eps"],
        "category": "估值指标",
        "display_name": "市盈率 PE",
        "formula_text": "PE = 股价 / 每股收益",
        "unit": "倍",
    },
    "pb_ratio": {
        "func": calc_pb_ratio,
        "params": ["stock_price", "bvps"],
        "category": "估值指标",
        "display_name": "市净率 PB",
        "formula_text": "PB = 股价 / 每股净资产",
        "unit": "倍",
    },
    # 现金流
    "free_cash_flow": {
        "func": calc_free_cash_flow,
        "params": ["operating_cf", "capital_expenditure"],
        "category": "现金流",
        "display_name": "自由现金流",
        "formula_text": "FCF = 经营活动现金流 - 资本支出",
        "unit": "元",
    },
    "cf_to_net_profit": {
        "func": calc_cf_to_net_profit,
        "params": ["operating_cf", "net_profit"],
        "category": "现金流",
        "display_name": "经营现金流/净利润比率",
        "formula_text": "现金流/净利比率 = 经营现金流 / 净利润 × 100%",
        "unit": "%",
    },
    # 杜邦分析
    "dupont": {
        "func": dupont_analysis,
        "params": ["net_profit", "revenue", "total_assets", "equity"],
        "category": "杜邦分析",
        "display_name": "杜邦分析",
        "formula_text": "ROE = 净利率 × 资产周转率 × 权益乘数",
        "unit": "复合",
    },
}


# ==================== 工具入口类 ====================

class FinancialCalcTool:
    """
    财务计算工具入口。

    用法:
        tool = FinancialCalcTool()
        result = tool.run("roe", {"net_profit": 862.28, "avg_equity": 2687.45})
        # {"success": True, "result": 32.08, "expression": "ROE = 862.28 / 2687.45 × 100% = 32.08%", ...}
    """

    def __init__(self):
        self.name = "financial_calc"

    def run(self, formula: str, **data_values) -> dict:
        """
        计算公式并返回结果。

        参数:
            formula: 公式名或逗号分隔的多公式（如 "roe" 或 "roe,net_profit_margin"）
            **data_values: 公式所需的参数值（如 revenue=1709.90, cost=...）

        返回（单公式）:
            {
                "success": True/False,
                "result": float or dict,
                "display_name": str,
                "category": str,
                "expression": str,
                "unit": str,
                "error": None or str,
            }

        返回（多公式批量）:
            {
                "success": True,    # 所有公式全部成功才为 True
                "results": [        # 每个公式的独立结果
                    {"formula": "roe", "success": True, "result": 32.08, ...},
                    {"formula": "net_profit_margin", "success": True, "result": 49.45, ...},
                ],
                "summary": "2/2 公式计算成功",
                "is_batch": True,   # 标记为批量结果
            }
        """
        params = data_values  # 从 executor 依赖注入的数据值

        # ── V6.0: 多公式批量计算 ──
        formula_names = [f.strip() for f in formula.split(",") if f.strip()]
        if len(formula_names) > 1:
            return self._batch_calculate(formula_names, params)

        # ── 单公式模式（原有逻辑）──
        return self._single_calculate(formula, params)

    def _single_calculate(self, formula: str, params: dict) -> dict:
        """单个公式计算（含 V7.0 智能参数补全）"""
        entry = FORMULA_REGISTRY.get(formula)
        if not entry:
            return {
                "success": False,
                "result": None,
                "display_name": formula,
                "category": "未知",
                "expression": "",
                "unit": "",
                "error": f"未知公式: {formula}，可用公式: {list(FORMULA_REGISTRY.keys())}",
            }

        try:
            # ── V7.0: 智能参数补全（ROE/ROA/Growth 自动回退）──
            params = self._auto_fill_params(formula, dict(params))

            func = entry["func"]
            # 提取所需参数
            args = []
            for param_name in entry["params"]:
                if param_name not in params:
                    raise ValueError(f"缺少参数: {param_name}")
                args.append(params[param_name])

            result = func(*args)

            # 构建计算表达式（简洁版：只显示公式名和结果，不暴露中间参数）
            expr = f"{entry['formula_text']} = {result}{entry['unit']}"

            return {
                "success": True,
                "result": result,
                "display_name": entry["display_name"],
                "category": entry["category"],
                "expression": expr,
                "unit": entry["unit"],
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "result": None,
                "display_name": entry.get("display_name", formula),
                "category": entry.get("category", "未知"),
                "expression": "",
                "unit": "",
                "error": str(e),
            }

    @staticmethod
    def _auto_fill_params(formula: str, params: dict) -> dict:
        """
        V7.0: 智能参数补全 — 修复 ROE/ROA/Growth 常见参数名不匹配。

        ROE 场景：只有 equity 无 avg_equity → avg_equity = equity
        ROA 场景：只有 total_assets 无 avg_total_assets → avg_total_assets = total_assets
        增长率场景：只有 营业收入_2024/营业收入_2023 → 提取 current_revenue/previous_revenue
        """
        params = dict(params)  # 不修改原始字典

        # ── ROE: avg_equity ← equity ──
        if formula == "roe":
            if "avg_equity" not in params and "equity" in params:
                params["avg_equity"] = params["equity"]

        # ── ROA: avg_total_assets ← total_assets ──
        if formula == "roa":
            if "avg_total_assets" not in params and "total_assets" in params:
                params["avg_total_assets"] = params["total_assets"]

        # ── 营收增长率: current_revenue ← 营业收入_最大年 ──
        if formula == "revenue_growth":
            if "current_revenue" not in params or "previous_revenue" not in params:
                yearly = FinancialCalcTool._extract_yearly(params, "营业收入")
                if len(yearly) >= 2:
                    sorted_yrs = sorted(yearly.keys(), reverse=True)
                    params.setdefault("current_revenue", yearly[sorted_yrs[0]])
                    params.setdefault("previous_revenue", yearly[sorted_yrs[1]])

        # ── 净利润增长率: current_profit ← 净利润_最大年 ──
        if formula == "net_profit_growth":
            if "current_profit" not in params or "previous_profit" not in params:
                yearly = FinancialCalcTool._extract_yearly(params, "净利润")
                if len(yearly) >= 2:
                    sorted_yrs = sorted(yearly.keys(), reverse=True)
                    params.setdefault("current_profit", yearly[sorted_yrs[0]])
                    params.setdefault("previous_profit", yearly[sorted_yrs[1]])

        return params

    @staticmethod
    def _extract_yearly(params: dict, metric_base: str) -> dict:
        """从 params 中提取带年份后缀的指标值，如 {'2024': 1709.90, '2023': 1505.60}"""
        import re
        pattern = re.compile(rf'^{re.escape(metric_base)}_(\d{{4}})$')
        result = {}
        for key, value in params.items():
            m = pattern.match(key)
            if m:
                result[int(m.group(1))] = value
        return result

    def _batch_calculate(self, formula_names: list, params: dict) -> dict:
        """
        批量计算多个公式。

        对每个公式调用 _single_calculate，汇总结果。
        注意：不同公式可能需要不同参数——每个公式独立尝试，缺参数则单独标记失败。
        """
        results = []
        success_count = 0
        for name in formula_names:
            r = self._single_calculate(name, params)
            r["formula"] = name
            if r["success"]:
                success_count += 1
            results.append(r)

        all_success = success_count == len(formula_names)
        summary_parts = [f"{r['formula']}: {r['result']}{r.get('unit','')}" for r in results if r["success"]]
        failed = [r["formula"] for r in results if not r["success"]]

        summary = f"批量计算 {success_count}/{len(formula_names)} 成功"
        if summary_parts:
            summary += ": " + "; ".join(summary_parts[:3])
        if failed:
            summary += f"；失败: {', '.join(failed)}"

        return {
            "success": all_success,
            "results": results,
            "summary": summary,
            "is_batch": True,
            "display_name": ", ".join(
                FORMULA_REGISTRY.get(n, {}).get("display_name", n) for n in formula_names
            ),
            "category": "批量计算",
            "error": None if all_success else f"部分公式失败: {', '.join(failed)}",
        }

    def list_formulas(self) -> List[dict]:
        """列出所有可用公式及参数"""
        return [
            {
                "name": name,
                "display_name": info["display_name"],
                "category": info["category"],
                "formula_text": info["formula_text"],
                "params": info["params"],
                "unit": info["unit"],
            }
            for name, info in FORMULA_REGISTRY.items()
        ]
