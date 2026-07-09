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
import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from loguru import logger

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
    "经营现金流": {"keys": ["operating_cf"], "formula": None},
    "投资现金流": {"keys": ["investing_cf"], "formula": None},
    "筹资现金流": {"keys": ["financing_cf"], "formula": None},
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
    metrics = [alias for alias in METRIC_ALIASES if alias in query]
    # 去重保序
    return symbols, years, list(dict.fromkeys(metrics))


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

        for year in years:
            values = {}
            for key in keys:
                record = db.query(FinancialData).filter(
                    FinancialData.symbol == symbol,
                    FinancialData.year == year,
                    FinancialData.quarter == "Q4",
                    FinancialData.metric_key == key,
                ).first()
                if not record:
                    record = db.query(FinancialData).filter(
                        FinancialData.symbol == symbol,
                        FinancialData.year == year,
                        FinancialData.metric_key == key,
                    ).order_by(FinancialData.quarter.desc()).first()
                if record:
                    values[key] = record.metric_value
                    found_any = True

            if not values:
                continue

            key_prefix = f"{short_name}_" if multi_company else ""
            year_suffix = f"_{year}" if len(years) > 1 else ""

            if formula and len(keys) >= 2 and all(k in values for k in keys):
                try:
                    safe_vars = {k: v for k, v in values.items() if k in keys}
                    result = eval(formula, {"__builtins__": {}}, safe_vars)
                    data[f"{key_prefix}{metric_name}{year_suffix}"] = round(result, 2)
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
