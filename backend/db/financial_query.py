"""
财务数据查询服务 — 自然语言 → SQL 查询

V8.0 核心组件：零 LLM 参与，纯规则匹配 + SQL 直查。

流程:
  用户问"茅台2024年ROE" →
    1. 公司识别: "茅台" → 600519
    2. 年份解析: "2024" → [2024]
    3. 指标匹配: "ROE" → 计算公式(net_profit_attr_parent / total_equity)
    4. SQL 查询 → 返回精确数值
    5. 如果 SQL 没数据 → 返回 None，调用方走 RAG 兜底

设计原则:
  - 零 LLM 参与（< 5ms）
  - 找不到数据 → 返回 None（不瞎猜）
  - 支持多年份、多指标批量查询
"""
import ast
import operator as _op
import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from loguru import logger

# ============ V8.1 D13: 安全数学表达式求值器（替换 eval） ============

# 白名单：仅允许数学运算的 AST 节点类型
# V8.2 修复：添加 ast.Load/ast.Store/ast.Del 上下文节点（变量引用标记，非可执行代码）
_ALLOWED_NODES = {ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant,
                  ast.Add, ast.Sub, ast.Mult, ast.Div,
                  ast.USub, ast.UAdd,
                  ast.Load, ast.Store, ast.Del}
_MAX_EXPR_LENGTH = 200  # 公式最大字符数，防止极端输入


def _safe_eval(expression: str, variables: dict) -> float:
    """
    安全地计算数学表达式，仅允许 + - * / 和变量引用。

    与 eval(expr, {"__builtins__": {}}, vars) 不同，此函数：
    - 使用 AST 白名单严格限制可执行的操作
    - 拒绝任何函数调用、属性访问、位运算、比较运算等
    - 限制表达式最大长度
    - 无 DoS 风险（如指数爆炸 `a**a**a`）

    抛出: ValueError（表达式不安全）或 ZeroDivisionError
    """
    if len(expression) > _MAX_EXPR_LENGTH:
        raise ValueError(f"表达式过长 ({len(expression)} > {_MAX_EXPR_LENGTH})")

    tree = ast.parse(expression.strip(), mode='eval')

    # 递归验证 AST 节点，确保所有节点类型在白名单内
    def _validate(node):
        if type(node) not in _ALLOWED_NODES:
            raise ValueError(f"不允许的操作: {type(node).__name__}")
        for child in ast.iter_child_nodes(node):
            _validate(child)

    _validate(tree)

    # 编译并执行（此时 AST 已通过安全验证）
    code = compile(tree, '<formula>', 'eval')
    # V8.2 修复：Python 3.12 中 code 对象没有 .eval() 方法，使用内置 eval()
    return eval(code, {"__builtins__": {}}, variables)

# ── 公司名 → symbol 映射 ──
COMPANY_ALIASES: Dict[str, str] = {
    # 白酒
    "贵州茅台": "600519", "茅台": "600519",
    "五粮液": "000858",
    "山西汾酒": "600809", "汾酒": "600809",
    "泸州老窖": "000568",
    "洋河股份": "002304", "洋河": "002304",
    # 新能源
    "比亚迪": "002594",
    "宁德时代": "300750", "宁德": "300750",
    "隆基绿能": "601012", "隆基": "601012",
    # 金融
    "招商银行": "600036", "招行": "600036",
    "中国平安": "601318", "平安": "601318",
    "平安银行": "000001",
    "中信证券": "600030",
    # 家电/科技/消费
    "美的集团": "000333", "美的": "000333",
    "格力电器": "000651", "格力": "000651",
    "恒瑞医药": "600276", "恒瑞": "600276",
    "海康威视": "002415", "海康": "002415",
    "科大讯飞": "002230",
    "伊利股份": "600887", "伊利": "600887",
    "长江电力": "600900",
    "京东方": "000725",
    "中芯国际": "688981",
}

# ── 指标别名 → 需要查的 metric_keys ──
# 简单指标：一个 metric_key 直接查
# 复合指标（如 ROE）：需要查多个 key 再计算
METRIC_ALIASES: Dict[str, dict] = {
    # 利润表指标（直接从 financial_data 取值）
    "营业收入": {"keys": ["revenue"], "formula": None},
    "营收": {"keys": ["revenue"], "formula": None},
    "营业成本": {"keys": ["cost_of_revenue"], "formula": None},
    "销售费用": {"keys": ["selling_expenses"], "formula": None},
    "管理费用": {"keys": ["admin_expenses"], "formula": None},
    "研发费用": {"keys": ["rd_expenses"], "formula": None},
    "财务费用": {"keys": ["finance_expenses"], "formula": None},
    "营业利润": {"keys": ["operating_profit"], "formula": None},
    "利润总额": {"keys": ["total_profit"], "formula": None},
    "净利润": {"keys": ["net_profit_attr_parent"], "formula": None},
    "归母净利润": {"keys": ["net_profit_attr_parent"], "formula": None},
    "每股收益": {"keys": ["eps"], "formula": None},
    "EPS": {"keys": ["eps"], "formula": None},
    # 资产负债表指标
    "总资产": {"keys": ["total_assets"], "formula": None},
    "净资产": {"keys": ["equity_attr_parent"], "formula": None},
    "总负债": {"keys": ["total_liabilities"], "formula": None},
    "流动资产": {"keys": ["current_assets"], "formula": None},
    "流动负债": {"keys": ["current_liabilities"], "formula": None},
    "货币资金": {"keys": ["cash_and_equivalents"], "formula": None},
    "存货": {"keys": ["inventory"], "formula": None},
    "固定资产": {"keys": ["fixed_assets"], "formula": None},
    "无形资产": {"keys": ["intangible_assets"], "formula": None},
    "商誉": {"keys": ["goodwill"], "formula": None},
    "长期借款": {"keys": ["long_term_borrowings"], "formula": None},
    "短期借款": {"keys": ["short_term_borrowings"], "formula": None},
    # 现金流指标
    "营收": {"keys": ["revenue"], "formula": None},  # 简短别名
    "净利": {"keys": ["net_profit_attr_parent"], "formula": None},
    "经营活动现金流净额": {"keys": ["operating_cf"], "formula": None},
    "经营活动产生的现金流量净额": {"keys": ["operating_cf"], "formula": None},
    "经营活动现金流": {"keys": ["operating_cf"], "formula": None},
    "经营现金流": {"keys": ["operating_cf"], "formula": None},
    "经营性现金流": {"keys": ["operating_cf"], "formula": None},
    "归属母公司净利润": {"keys": ["net_profit_attr_parent"], "formula": None},
    "投资现金流": {"keys": ["investing_cf"], "formula": None},
    "筹资现金流": {"keys": ["financing_cf"], "formula": None},
    # 权益/资产补充别名（LLM 常用术语）
    "所有者权益": {"keys": ["equity_attr_parent"], "formula": None},
    "股东权益": {"keys": ["equity_attr_parent"], "formula": None},
    "资本支出": {"keys": ["fixed_assets"], "formula": None},  # V8.4: 自由现金流用，以固定资产近似
    "capex": {"keys": ["fixed_assets"], "formula": None},
    # ── 复合指标（需要查多个 key 再计算）──
    "毛利率": {
        "keys": ["revenue", "cost_of_revenue"],
        "formula": "(revenue - cost_of_revenue) / revenue * 100",
    },
    "净利率": {
        "keys": ["net_profit_attr_parent", "revenue"],
        "formula": "net_profit_attr_parent / revenue * 100",
    },
    "ROE": {
        "keys": ["net_profit_attr_parent", "equity_attr_parent"],
        "formula": "net_profit_attr_parent / equity_attr_parent * 100",
    },
    "净资产收益率": {
        "keys": ["net_profit_attr_parent", "equity_attr_parent"],
        "formula": "net_profit_attr_parent / equity_attr_parent * 100",
    },
    "ROA": {
        "keys": ["net_profit_attr_parent", "total_assets"],
        "formula": "net_profit_attr_parent / total_assets * 100",
    },
    "资产负债率": {
        "keys": ["total_liabilities", "total_assets"],
        "formula": "total_liabilities / total_assets * 100",
    },
    "权益乘数": {
        "keys": ["total_assets", "equity_attr_parent"],
        "formula": "total_assets / equity_attr_parent",
    },
    "自由现金流": {
        "keys": ["operating_cf", "fixed_assets"],
        "formula": "operating_cf - fixed_assets",
    },
}


def parse_query(query: str) -> Tuple[List[str], List[int], List[str]]:
    """
    解析自然语言查询 → (symbols, years, metric_names)

    返回:
        (symbols, years, metrics) — symbols为空表示无法识别公司
    """
    # 1. 公司识别（支持多公司）
    symbols = []
    for alias, sym in COMPANY_ALIASES.items():
        if alias in query:
            symbols.append(sym)
    symbols = list(dict.fromkeys(symbols))  # 去重保序

    # 2. 年份提取
    now = datetime.now()
    years = []
    # 数字年份: "2024年" / "2024"
    year_matches = re.findall(r"(20\d{2})\s*年?", query)
    years.extend(int(y) for y in year_matches)
    # 口语化: "去年" / "今年" / "前年"
    if "去年" in query:
        years.append(now.year - 1)
    if "今年" in query:
        years.append(now.year)
    if "前年" in query:
        years.append(now.year - 2)
    # 范围: "2022-2024" / "近3年"
    range_match = re.search(r"(20\d{2})\s*[-~至到]\s*(20\d{2})", query)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        years.extend(range(start, end + 1))
    if "近" in query and "年" in query:
        n_match = re.search(r"近\s*(\d+)\s*年", query)
        if n_match:
            n = int(n_match.group(1))
            years.extend(range(now.year - n, now.year))
    # 去重排序
    years = sorted(set(years))

    if not years:
        years = [now.year - 1]

    # 3. 指标匹配
    # 直接匹配: query 中包含完整的别名 → 精确命中
    raw_metrics = [alias for alias in METRIC_ALIASES if alias in query]
    raw_metrics = list(dict.fromkeys(raw_metrics))  # 去重
    # 去子串: 短别名是长别名的子串时，保留长的（如 "净利" ⊂ "净利率", "营收" ⊂ "营业收入"）
    metrics = []
    for m in raw_metrics:
        dup = False
        for other in raw_metrics:
            if other != m and m in other:
                dup = True  # m 是 other 的子串 → 丢弃短的 m
                break
        if not dup:
            metrics.append(m)
    return symbols, years, metrics


def _query_one_company(db, symbol: str, years: List[int], metrics: List[str],
                       multi_company: bool) -> Optional[dict]:
    """查询一家公司的指标数据。multi_company=True 时键名加公司前缀。"""
    from db import SessionLocal, FinancialData, Company

    company = db.query(Company).filter(Company.symbol == symbol).first()
    if not company:
        return None

    # 取公司简称用于键名前缀
    short_name = company.name.replace("贵州", "").replace("股份", "").replace("有限", "") if company.name else symbol
    data = {}
    found_any = False

    for metric_name in metrics:
        metric_def = METRIC_ALIASES[metric_name]
        keys = metric_def["keys"]
        formula = metric_def["formula"]

        # V8.3: 同比对比时统一季度口径。先检查所有年份 Q4 是否都存在
        all_have_q4 = True
        for year in years:
            for key in keys:
                q4 = db.query(FinancialData).filter(
                    FinancialData.symbol == symbol,
                    FinancialData.year == year,
                    FinancialData.quarter == "Q4",
                    FinancialData.metric_key == key,
                ).first()
                if not q4:
                    all_have_q4 = False
                    break
            if not all_have_q4:
                break

        # 统一取每个年份的最新可用季度（确保年份间可对比）
        target_quarter = "Q4" if all_have_q4 else None

        for year in years:
            values = {}
            for key in keys:
                query_base = db.query(FinancialData).filter(
                    FinancialData.symbol == symbol,
                    FinancialData.year == year,
                    FinancialData.metric_key == key,
                )
                if target_quarter:
                    record = query_base.filter(FinancialData.quarter == target_quarter).first()
                else:
                    # 各年份都取各自最新季度，保持同季可比
                    record = query_base.order_by(FinancialData.quarter.desc()).first()
                if record:
                    values[key] = record.metric_value
                    found_any = True

            if not values:
                continue

            key_prefix = f"{short_name}_" if multi_company else ""
            year_suffix = f"_{year}"  # V8.3: 始终带年份，确保增长公式能区分当期/上期

            if formula and len(keys) >= 2 and all(k in values for k in keys):
                try:
                    safe_vars = {k: v for k, v in values.items() if k in keys}
                    # V8.1 D13: 用 AST 白名单求值器替换 eval，仅允许 + - * /
                    result = _safe_eval(formula, safe_vars)
                    data[f"{key_prefix}{metric_name}{year_suffix}"] = round(result, 2)
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    logger.debug(f"公式计算失败 [{formula}]: {e}")
                    continue
                except Exception:
                    continue
            elif not formula:
                for key, val in values.items():
                    if key in keys:
                        data[f"{key_prefix}{metric_name}{year_suffix}"] = val

    if not found_any:
        return None
    return {"company": company, "data": data, "found_any": found_any}


def try_query(query: str) -> Optional[dict]:
    """
    尝试用 SQL 回答查询。支持多公司（每家公司独立查询，键名加公司前缀）。

    返回:
        成功: {"found": True, "data": {...}, "summary": "...", "confidence": 0.99, "source": "SQL"}
        失败: None
    """
    # 1. 解析查询
    symbols, years, metrics = parse_query(query)
    if not symbols:
        logger.debug(f"[SQL] 未识别公司: {query[:50]}")
        return None
    if not metrics:
        logger.debug(f"[SQL] 未识别指标: {query[:50]}")
        return None

    multi = len(symbols) > 1
    logger.info(f"[SQL] 解析: {symbols} × {years} × {metrics}")

    from db import SessionLocal
    db = SessionLocal()
    try:
        all_data = {}
        company_names = []
        any_found = False

        for sym in symbols:
            result = _query_one_company(db, sym, years, metrics, multi)
            if result:
                all_data.update(result["data"])
                company_names.append(result["company"].name or sym)
                any_found = True

        if not any_found:
            return None

        # 生成摘要
        if multi:
            summary = " vs ".join(company_names) + f" {years[0]}年 对比"
        elif len(years) == 1:
            summary = f"{company_names[0]} {years[0]}年"
        else:
            summary = f"{company_names[0]} {years[0]}-{years[-1]}年"

        return {
            "found": True,
            "data": all_data,
            "summary": summary,
            "raw_chunks": [],
            "confidence": 0.99,
            "source": "SQL",
        }
    except Exception as e:
        logger.warning(f"[SQL] 查询失败: {e}")
        return None
    finally:
        try:
            db.close()
        except Exception:
            pass
