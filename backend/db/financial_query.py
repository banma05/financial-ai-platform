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


def parse_query(query: str) -> Tuple[Optional[str], List[int], List[str]]:
    """
    解析自然语言查询 → (symbol, years, metric_names)

    参数:
        query: 如"茅台2024年ROE和毛利率"

    返回:
        (symbol, years, metrics) — symbol为None表示无法识别公司
    """
    # 1. 公司识别（支持多公司）
    symbols = []
    for alias, sym in COMPANY_ALIASES.items():
        if alias in query:
            symbols.append(sym)
    symbols = list(dict.fromkeys(symbols))  # 去重保序
    symbol = symbols[0] if symbols else None

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
    return symbol, years, list(dict.fromkeys(metrics))


def try_query(query: str) -> Optional[dict]:
    """
    尝试用 SQL 回答查询。无法处理返回 None。

    参数:
        query: 自然语言查询

    返回:
        成功: {"found": True, "data": {...}, "summary": "...", "confidence": 0.99}
        失败: None
    """
    # 1. 解析查询
    symbol, years, metrics = parse_query(query)
    if not symbol:
        logger.debug(f"[SQL] 未识别公司: {query[:50]}")
        return None
    if not metrics:
        logger.debug(f"[SQL] 未识别指标: {query[:50]}")
        return None

    logger.info(f"[SQL] 解析: {symbol} × {years} × {metrics}")

    # 2. 查询数据库
    from db import SessionLocal, FinancialData, Company
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.symbol == symbol).first()
        if not company:
            logger.debug(f"[SQL] 公司未注册: {symbol}")
            return None

        data = {}
        found_any = False

        for metric_name in metrics:
            metric_def = METRIC_ALIASES[metric_name]
            keys = metric_def["keys"]
            formula = metric_def["formula"]

            for year in years:
                values = {}
                for key in keys:
                    # 取 Q4（年报）优先，没有则取最近可用季度
                    record = db.query(FinancialData).filter(
                        FinancialData.symbol == symbol,
                        FinancialData.year == year,
                        FinancialData.quarter == "Q4",
                        FinancialData.metric_key == key,
                    ).first()

                    if not record:
                        # 尝试其他季度
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

                if formula and len(keys) >= 2 and all(k in values for k in keys):
                    # 复合指标：用公式计算（所有分量都有值才计算）
                    try:
                        safe_vars = {k: v for k, v in values.items() if k in keys}
                        result = eval(formula, {"__builtins__": {}}, safe_vars)
                        if len(years) == 1:
                            data[metric_name] = round(result, 2)
                        else:
                            data[f"{metric_name}_{year}"] = round(result, 2)
                    except Exception:
                        continue
                elif not formula:
                    # 简单指标：直接取值
                    for key, val in values.items():
                        if key in keys:
                            if len(years) == 1:
                                data[metric_name] = val
                            else:
                                data[f"{metric_name}_{year}"] = val

        if not found_any:
            db.close()
            logger.debug(f"[SQL] 无数据: {symbol} {years}")
            return None

        db.close()

        # 3. 生成摘要
        company_name = company.name or symbol
        if len(years) == 1:
            summary_parts = [f"{company_name} {years[0]}年"]
            for m in metrics:
                key = m
                if key in data:
                    val = data[key]
                    summary_parts.append(f"{m}={val:,.2f}")
        else:
            summary_parts = [f"{company_name} {years[0]}-{years[-1]}年"]
        summary = "，".join(summary_parts)

        return {
            "found": True,
            "data": data,
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
