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

            # ── V8.3: 合理性校验 — 财务数据宁缺毋滥 ──
            sanity = FinancialCalcTool._sanity_check(formula, result, params)
            if not sanity["ok"]:
                return {
                    "success": False,
                    "result": None,
                    "display_name": entry["display_name"],
                    "category": entry["category"],
                    "expression": "",
                    "unit": entry["unit"],
                    "error": sanity["reason"],
                }

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
    def _sanity_check(formula: str, result: float, params: dict) -> dict:
        """
        V8.3: 计算结果合理性校验。

        财务分析宁缺毋滥——数值超出合理范围说明输入数据有问题，
        不应输出给用户。
        """
        checks = {
            "roe": (0, 200, "ROE 超出合理范围 (0-200%)，可能净资产数据有误"),
            "roa": (0, 100, "ROA 超出合理范围 (0-100%)，可能总资产数据有误"),
            "gross_profit_margin": (0, 100, "毛利率超出合理范围 (0-100%)"),
            "net_profit_margin": (0, 100, "净利率超出合理范围 (0-100%)"),
            "debt_ratio": (0, 100, "资产负债率超出合理范围 (0-100%)"),
            "revenue_growth": (-500, 500, "营收增长率超出合理范围 (-500%~500%)，可能年份数据错配"),
            "net_profit_growth": (-500, 500, "净利润增长率超出合理范围 (-500%~500%)，可能年份数据错配"),
        }
        if formula in checks:
            lo, hi, reason = checks[formula]
            if not (lo <= result <= hi):
                return {"ok": False, "reason": f"{reason}（计算值: {result}%）"}
        return {"ok": True}

    @staticmethod
    def _auto_fill_params(formula: str, params: dict) -> dict:
        """
        V8.3: 智能参数补全 — 三种策略覆盖所有公式缺参场景。

        策略1 (avg_* 回退): avg_equity←equity, avg_total_assets←total_assets 等
        策略2 (增长公式): 从年份后缀键名提取 current/previous 对
        策略3 (负债率/流动率): 从已有数据推算缺失参数
        """
        params = dict(params)

        # ── 策略0: 年份后缀通用回退（revenue_2024 → revenue）──
        # ParamInjector 注入的是英文名_年份（如 revenue_2024）
        # 公式参数名不帶年份（如 revenue），此处从 _YYYY 键自动回退
        # 必须放在最前面，让策略1-4 都能利用回退后的无后缀参数
        import re as _re
        _yearly: dict[str, dict[int, float]] = {}
        for _k, _v in params.items():
            if not isinstance(_v, (int, float)):
                continue
            _m = _re.match(r'^(.+?)_(\d{4})$', str(_k))
            if _m:
                _base_name, _yr = _m.group(1), int(_m.group(2))
                _yearly.setdefault(_base_name, {})[_yr] = _v
        for _base_name, _years in _yearly.items():
            if _base_name not in params:
                _latest_yr = max(_years.keys())
                params.setdefault(_base_name, _years[_latest_yr])

        # ── 策略1: avg_* 回退（覆盖 ROE/ROA/周转率等 6 个公式）──
        avg_fallbacks = {
            "avg_equity": "equity",
            "avg_total_assets": "total_assets",
            "avg_inventory": "inventory",
            "avg_receivables": "receivables",
        }
        for avg_key, fallback_key in avg_fallbacks.items():
            if avg_key not in params and fallback_key in params:
                params[avg_key] = params[fallback_key]

        # ── 策略2: 增长公式 — 从年份后缀键名提取当期/上期 ──
        growth_formulas = {
            "revenue_growth": ("营业收入", "current_revenue", "previous_revenue"),
            "net_profit_growth": ("净利润", "current_profit", "previous_profit"),
        }
        if formula in growth_formulas:
            metric, cur_key, prev_key = growth_formulas[formula]
            if cur_key not in params or prev_key not in params:
                yearly = FinancialCalcTool._extract_yearly(params, metric)
                if len(yearly) >= 2:
                    sorted_yrs = sorted(yearly.keys(), reverse=True)
                    params.setdefault(cur_key, yearly[sorted_yrs[0]])
                    params.setdefault(prev_key, yearly[sorted_yrs[1]])

        # ── 策略3: 负债 ← 总资产 - 净资产（数据查询常缺负债项）──
        if formula == "debt_ratio":
            if "total_liabilities" not in params:
                if "total_assets" in params and "equity" in params:
                    params["total_liabilities"] = round(params["total_assets"] - params["equity"], 2)

        # ── 策略4: 流动比率 — current_assets/current_liabilities 缺一不可时不补（安全）──
        # 不自动推算，避免错误

        # ── 策略5: bvps(每股净资产) — 从 equity + net_profit + eps 推算 ──
        if formula == "pb_ratio" and "bvps" not in params:
            equity = (params.get("equity") or params.get("equity_attr_parent")
                      or params.get("净资产") or params.get("所有者权益"))
            net_profit = (params.get("net_profit") or params.get("net_profit_attr_parent")
                          or params.get("净利润"))
            eps_key = params.get("eps") or params.get("每股收益")
            # 如果 EPS 不在顶层，从年份键中提取（如 eps_2024 / 每股收益_2024）
            if eps_key is None:
                import re as _re2
                for k, v in params.items():
                    if _re2.match(r'(eps|每股收益)_\d{4}$', str(k)):
                        eps_key = v
                        break
            if equity and net_profit and eps_key and eps_key != 0:
                total_shares = net_profit / eps_key  # EPS = 净利润/总股本 → 总股本 = 净利润/EPS
                params["bvps"] = round(equity / total_shares, 2)

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

        V8.4: 杜邦分析返回 dict，在此展开为独立标量条目，
        确保下游（executor/reporter/chart）只看到标量结果。
        """
        results = []
        success_count = 0
        for name in formula_names:
            r = self._single_calculate(name, params)
            r["formula"] = name
            if r["success"]:
                success_count += 1
                # 杜邦分析返回 dict → 展开为独立子指标
                if isinstance(r.get("result"), dict):
                    dupont_dict = r["result"]
                    r["_expanded"] = True  # 标记：原始结果已被展开
                    for sub_key, sub_val in dupont_dict.items():
                        if isinstance(sub_val, (int, float)):
                            # 为子指标创建独立的计算结果条目
                            sub_entry = {
                                "formula": f"dupont_{sub_key}",
                                "success": True,
                                "result": sub_val,
                                "display_name": f"杜邦-{self._dupont_sub_name(sub_key)}",
                                "category": "杜邦分析",
                                "expression": f"杜邦分析子项: {sub_key} = {sub_val}",
                                "unit": self._dupont_sub_unit(sub_key),
                                "_from_dupont": True,
                            }
                            results.append(sub_entry)
                            success_count += 1
                    # 保留原始条目（含 breakdown 文本，供报告展示用）
                    # 但把 result 设为 None，避免 dict 污染下游
                    r["result"] = None
                results.append(r)
            else:
                results.append(r)

        all_success = success_count == len(formula_names)
        summary_parts = [f"{r['formula']}: {r['result']}{r.get('unit','')}"
                        for r in results if r["success"] and r["result"] is not None]
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

    @staticmethod
    def _dupont_sub_name(key: str) -> str:
        """杜邦分析子项中文名"""
        mapping = {
            "roe": "ROE", "net_profit_margin": "净利率",
            "asset_turnover": "资产周转率", "equity_multiplier": "权益乘数",
        }
        return mapping.get(key, key)

    @staticmethod
    def _dupont_sub_unit(key: str) -> str:
        """杜邦分析子项单位"""
        mapping = {
            "roe": "%", "net_profit_margin": "%",
            "asset_turnover": "次", "equity_multiplier": "倍",
        }
        return mapping.get(key, "")

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
