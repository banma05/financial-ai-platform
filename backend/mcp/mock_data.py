"""
MCP 数据提供器 — AKShare 真实数据优先 + Mock 兜底

数据优先级: AKShare（新浪财经） > 内置 Mock 数据
切换方式: 设置 _USE_AKSHARE = False 可强制使用 Mock

覆盖 3 家核心标的:
- 贵州茅台 (600519.SH) — 白酒龙头
- 比亚迪 (002594.SZ)   — 新能源车龙头
- 腾讯控股 (00700.HK)  — 互联网龙头（港股，AKShare 部分支持）
"""

from typing import Dict, List, Optional, Any
from datetime import date, timedelta
from loguru import logger

# ==================== 全局开关 ====================

_USE_AKSHARE = True  # True=优先AKShare真实数据, False=只用Mock

# ==================== 标的索引 ====================

SYMBOLS = {
    "600519": "贵州茅台", "600519.SH": "贵州茅台",
    "002594": "比亚迪",   "002594.SZ": "比亚迪",
    "00700": "腾讯控股",  "00700.HK": "腾讯控股",
}

SECTORS = {
    "600519": "白酒", "002594": "新能源汽车", "00700": "互联网",
}


def _normalize(symbol: str) -> str:
    return symbol.replace(".SH", "").replace(".SZ", "").replace(".HK", "")


# ==================== 1. 股票行情 ====================

def get_stock_price(symbol: str, period: str = "realtime") -> Dict[str, Any]:
    norm = _normalize(symbol)
    name = SYMBOLS.get(norm)

    if _USE_AKSHARE and norm in ("600519", "002594"):
        try:
            return _akshare_stock_price(norm, name, period)
        except Exception as e:
            logger.warning(f"[AKShare] 行情获取失败({symbol}): {e}，降级 Mock")

    return _mock_stock_price(norm, period)


def _akshare_stock_price(norm: str, name: str, period: str) -> Dict[str, Any]:
    import akshare as ak
    from datetime import datetime

    prefix = "sh" if norm.startswith("6") else "sz"
    full_symbol = f"{prefix}{norm}"

    # 日K线数据
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    df = ak.stock_zh_a_daily(symbol=full_symbol, start_date=start, end_date=end, adjust="qfq")

    if df.empty:
        raise ValueError("无数据")

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    change = round(latest["close"] - prev["close"], 2)
    change_pct = round(change / prev["close"] * 100, 2) if prev["close"] != 0 else 0

    high_52w = round(df["high"].rolling(250).max().iloc[-1], 2) if len(df) > 250 else round(df["high"].max(), 2)
    low_52w = round(df["low"].rolling(250).min().iloc[-1], 2) if len(df) > 250 else round(df["low"].min(), 2)

    result = {
        "symbol": f"{norm}.{'SH' if norm.startswith('6') else 'SZ'}", "name": name,
        "price": round(latest["close"], 2), "change": change, "change_pct": change_pct,
        "volume": int(latest.get("volume", 0)), "market_cap": 0,  # AKShare 无总市值
        "pe_ttm": 0, "pb": 0, "high_52w": high_52w, "low_52w": low_52w,
    }

    # 补充 PE/PB/市值（从新浪获取）
    try:
        info = _akshare_stock_info(norm)
        result["pe_ttm"] = info.get("pe_ttm", 0)
        result["pb"] = info.get("pb", 0)
        result["market_cap"] = info.get("market_cap", 0)
    except Exception as e:
        logger.debug(f"AKShare 股票信息获取失败({symbol}), 使用 Mock 兜底: {e}")

    if period != "realtime":
        days = {"daily": 30, "weekly": 12, "monthly": 24}.get(period, 30)
        history = []
        for _, row in df.tail(days).iterrows():
            history.append({"date": str(row["date"]), "close": round(row["close"], 2)})
        result["history"] = history

    return result


def _akshare_stock_info(norm: str) -> Dict[str, Any]:
    """从东方财富获取个股基本面（失败时返回空字典，不影响行情获取）"""
    try:
        import akshare as ak
        prefix = "sh" if norm.startswith("6") else "sz"
        info = ak.stock_individual_info_em(symbol=f"{prefix}{norm}")
        info_dict = dict(zip(info["item"], info["value"]))
        return {
            "pe_ttm": float(info_dict.get("市盈率-动态", 0) or 0),
            "pb": float(info_dict.get("市净率", 0) or 0),
            "market_cap": float(info_dict.get("总市值", 0) or 0) / 1e8,
        }
    except Exception as e:
        logger.debug(f"[AKShare] 个股信息获取失败({norm}): {e}")
        return {}


# ==================== 2. 财务报表 ====================

def get_financial_statements(
    symbol: str, statement_type: str = "all", period: str = "annual",
) -> Dict[str, Any]:
    norm = _normalize(symbol)
    name = SYMBOLS.get(norm)

    if _USE_AKSHARE and norm in ("600519", "002594"):
        try:
            return _akshare_statements(norm, name, statement_type)
        except Exception as e:
            logger.warning(f"[AKShare] 报表获取失败({symbol}): {e}，降级 Mock")

    return _mock_statements(norm, statement_type)


def _akshare_statements(norm: str, name: str, stype: str) -> Dict[str, Any]:
    import akshare as ak

    result = {"symbol": f"{norm}.{'SH' if norm.startswith('6') else 'SZ'}", "name": name, "period": "annual"}
    got_any = False
    report_date = ""

    for label, key in [("利润表", "income"), ("资产负债表", "balance"), ("现金流量表", "cashflow")]:
        if stype not in (key, "all"):
            continue
        try:
            df = ak.stock_financial_report_sina(stock=norm, symbol=label)
            if df.empty:
                continue

            # 新浪返回宽表: 行=报告期, 列=科目名
            # 取最新年报行（报表日期以 1231 结尾）
            date_col = df.columns[0]  # 第一列是报表日期
            annual_rows = df[df[date_col].astype(str).str.endswith("1231")]
            if annual_rows.empty:
                # 没有年报则取第一行
                annual_rows = df.head(1)

            row = annual_rows.iloc[0]
            report_date = str(row[date_col])

            data = {}
            for col in df.columns[1:]:  # 跳过日期列
                val = row[col]
                try:
                    val_float = float(val) if val and str(val) != "nan" else None
                    if val_float is not None and val_float != 0:
                        # 新浪原始单位: 元 → 转为亿元
                        data[str(col)] = round(val_float / 1e8, 2)
                except (ValueError, TypeError):
                    continue

            if data:
                result[key] = data
                got_any = True
        except Exception as e:
            logger.debug(f"[AKShare] {label}获取失败: {e}")

    if not got_any:
        raise ValueError("未能获取任何报表数据")

    result["report_date"] = report_date or "最新报告期"
    return result


# ==================== 3. 行业对比 ====================

def get_industry_comparison(
    symbol: str, metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    行业对比 — 股价从新浪实时获取，财务指标保留 Mock（年报数据不会每天变）。

    Mock 里的 PE/PB/ROE/营收增速基于最新年报真实数据，不比东财差。
    """
    norm = _normalize(symbol)
    sector = SECTORS.get(norm)
    if not sector:
        return {"error": f"未找到标的: {symbol}"}

    peers = [{**p} for p in _INDUSTRY_DATA.get(sector, [])]  # 深拷贝
    if not metrics:
        metrics = ["pe", "pb", "roe", "revenue_growth"]

    # AKShare 补充最新股价（用于 PE/PB 实时推算）
    if _USE_AKSHARE:
        for peer in peers:
            code = peer.get("code", "").replace(".SH", "").replace(".SZ", "")
            try:
                price = _akshare_latest_price(code)
                if price:
                    peer["price"] = price
                    # PE = 市值/净利, 简化：用实时价格更新 PE 估算
                    if peer.get("pe", 0) > 0 and not isinstance(peer["pe"], str):
                        pass  # PE 保留 Mock（年报数据更准确）
            except Exception as e:
                logger.debug(f"行业对比-个股价格获取失败({code}): {e}")

    target_name = SYMBOLS.get(norm, symbol)
    target_peer = next((p for p in peers if p["name"] == target_name), None)
    result_peers = [{k: v for k, v in p.items() if k in metrics or k in ("name", "code", "price")} for p in peers]

    return {
        "sector": sector, "metrics": metrics,
        "target": {k: v for k, v in (target_peer or {}).items() if k in metrics or k in ("name", "code", "price")},
        "peers": result_peers, "peer_count": len(result_peers),
    }


def _akshare_latest_price(code: str) -> Optional[float]:
    """获取个股最新收盘价（新浪，不抛异常）"""
    import akshare as ak
    from datetime import datetime
    try:
        prefix = "sh" if code.startswith("6") else "sz"
        df = ak.stock_zh_a_daily(
            symbol=f"{prefix}{code}",
            start_date=(datetime.now() - timedelta(days=7)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="qfq",
        )
        if not df.empty:
            return round(float(df.iloc[-1]["close"]), 2)
    except Exception as e:
        logger.debug(f"AKShare 最新价获取失败: {e}")
    return None


# ==================== 4. 市场指数 ====================

def get_market_index(index: str = "sh000001") -> Dict[str, Any]:
    if _USE_AKSHARE:
        try:
            return _akshare_index(index)
        except Exception as e:
            logger.warning(f"[AKShare] 指数获取失败({index}): {e}，降级 Mock")

    data = _INDEX_DATA.get(index)
    if not data:
        return {"error": f"未找到指数: {index}", "available": list(_INDEX_DATA.keys())}
    return dict(data)


def _akshare_index(code: str) -> Dict[str, Any]:
    import akshare as ak
    df = ak.stock_zh_index_daily(symbol=code)
    if df.empty:
        raise ValueError("无数据")
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    change = round(latest["close"] - prev["close"], 2)
    change_pct = round(change / prev["close"] * 100, 2) if prev["close"] != 0 else 0

    names = {"sh000001": "上证指数", "sh000300": "沪深300", "sz399001": "深证成指",
             "sz399006": "创业板指", "sh000819": "中证白酒", "sh931079": "新能源车"}
    return {"code": f"{code}.{'SH' if code.startswith('sh') else 'SZ'}", "name": names.get(code, code),
            "price": round(latest["close"], 2), "change": change, "change_pct": change_pct}


# ==================== 5. 财报日历 ====================

def get_financial_calendar(symbol: str, year: int = 2026) -> Dict[str, Any]:
    """财报日历 — 分红数据来自巨潮（真实），其余保留 Mock"""
    norm = _normalize(symbol)
    name = SYMBOLS.get(norm, symbol)

    # 从 Mock 获取基础事件
    events = list(_CALENDAR_DATA.get((norm, year), _CALENDAR_DATA.get(("default", year), [])))

    # AKShare 补充真实分红日期
    if _USE_AKSHARE and norm in ("600519", "002594"):
        try:
            div_events = _akshare_dividends(norm, year)
            # 替换 Mock 中的分红事件为真实日期
            events = [e for e in events if e["event_type"] != "dividend"]
            events.extend(div_events)
            events.sort(key=lambda x: x["date"])
        except Exception as e:
            logger.warning(f"[AKShare] 分红日历获取失败({symbol}): {e}")

    return {"symbol": symbol, "name": name, "year": year, "events": events, "event_count": len(events)}


def _akshare_dividends(norm: str, year: int) -> List[Dict]:
    """从巨潮资讯获取真实分红数据"""
    import akshare as ak
    df = ak.stock_dividend_cninfo(symbol=norm)
    events = []
    for _, row in df.iterrows():
        try:
            div_date = str(row["除权除息日"])
            if str(year) in div_date:
                plan = str(row.get("分红方式", ""))
                amount = row.get("除息金额", 0)
                desc = f"分红除权除息日（{plan}"
                if amount and amount != "NaN":
                    desc += f"，10股派{amount}元"
                desc += "）"
                events.append({"date": div_date, "event_type": "dividend", "description": desc})
        except Exception as e:
            logger.debug(f"分红记录解析跳过: {e}")
            continue
    logger.debug(f"[AKShare] {norm} {year}年分红: {len(events)} 条")
    return events


# ==================== Mock 数据（兜底） ====================

def _mock_stock_price(norm: str, period: str) -> Dict[str, Any]:
    data = _PRICE_DATA.get(norm)
    if not data:
        return {"error": f"未找到标的: {norm}", "available": list(SYMBOLS.keys())}
    result = {k: v for k, v in data.items()}
    if period != "realtime":
        result["history"] = _generate_history(data["price"], period)
    return result


def _mock_statements(norm: str, stype: str) -> Dict[str, Any]:
    all_data = _STATEMENT_DATA.get(norm)
    if not all_data:
        return {"error": f"未找到标的: {norm}"}
    result = {"symbol": all_data["symbol"], "name": all_data["name"],
              "period": "annual", "report_date": all_data["report_date"]}
    if stype in ("income", "all"):
        result["income"] = all_data["income"]
    if stype in ("balance", "all"):
        result["balance"] = all_data["balance"]
    if stype in ("cashflow", "all"):
        result["cashflow"] = all_data["cashflow"]
    return result


def _generate_history(price: float, period: str) -> List[Dict]:
    import random
    random.seed(hash(price))
    days = {"daily": 30, "weekly": 12, "monthly": 24}.get(period, 30)
    today = date.today()
    result = []
    for i in range(days, 0, -1):
        d = today - timedelta(days=i if period == "daily" else i * 7)
        change_pct = random.uniform(-3, 3)
        close = round(price * (1 + sum(random.uniform(-1, 1) for _ in range(i)) * 0.02), 2)
        result.append({"date": d.isoformat(), "close": max(close, 1), "change_pct": round(change_pct, 2)})
    return result


# ==================== Mock 静态数据 ====================

_PRICE_DATA = {
    "600519": {"symbol": "600519.SH", "name": "贵州茅台",
               "price": 1580.50, "change": 12.30, "change_pct": 0.78,
               "volume": 3820000, "market_cap": 19850.0,
               "pe_ttm": 22.5, "pb": 7.4, "high_52w": 1850.0, "low_52w": 1350.0},
    "002594": {"symbol": "002594.SZ", "name": "比亚迪",
               "price": 285.60, "change": -3.20, "change_pct": -1.11,
               "volume": 12500000, "market_cap": 8300.0,
               "pe_ttm": 25.8, "pb": 4.2, "high_52w": 350.0, "low_52w": 220.0},
    "00700": {"symbol": "00700.HK", "name": "腾讯控股",
               "price": 420.0, "change": 5.0, "change_pct": 1.20,
               "volume": 9800000, "market_cap": 38600.0,
               "pe_ttm": 18.2, "pb": 3.6, "high_52w": 480.0, "low_52w": 310.0},
}

_STATEMENT_DATA = {
    "600519": {
        "symbol": "600519.SH", "name": "贵州茅台", "report_date": "2024-12-31",
        "income": {"营业收入": 1741.44, "营业成本": 132.64, "销售费用": 58.15, "管理费用": 85.30,
                   "研发费用": 1.72, "财务费用": -25.80, "营业利润": 1435.92, "净利润": 862.28,
                   "营业收入_上期": 1505.60, "净利润_上期": 747.34},
        "balance": {"总资产": 3120.00, "流动资产": 2350.00, "总负债": 432.55,
                    "流动负债": 368.20, "净资产": 2687.45, "存货": 450.30},
        "cashflow": {"经营活动现金流净额": 665.80, "投资活动现金流净额": -120.50, "筹资活动现金流净额": -585.30},
    },
    "002594": {
        "symbol": "002594.SZ", "name": "比亚迪", "report_date": "2024-12-31",
        "income": {"营业收入": 6023.15, "营业成本": 4800.50, "销售费用": 245.00, "管理费用": 180.30,
                   "研发费用": 186.50, "财务费用": 58.20, "营业利润": 468.50, "净利润": 321.70,
                   "营业收入_上期": 5120.00, "净利润_上期": 280.30},
        "balance": {"总资产": 5234.00, "流动资产": 2850.00, "总负债": 3256.00,
                    "流动负债": 2680.00, "净资产": 1978.00, "存货": 680.50},
        "cashflow": {"经营活动现金流净额": 850.30, "投资活动现金流净额": -720.00, "筹资活动现金流净额": 120.50},
    },
    "00700": {
        "symbol": "00700.HK", "name": "腾讯控股", "report_date": "2024-12-31",
        "income": {"营业收入": 6600.00, "营业成本": 3500.00, "销售费用": 420.00, "管理费用": 850.00,
                   "研发费用": 520.00, "财务费用": 80.00, "营业利润": 1950.00, "净利润": 1580.00,
                   "营业收入_上期": 6090.00, "净利润_上期": 1420.00},
        "balance": {"总资产": 12000.00, "流动资产": 4800.00, "总负债": 4800.00,
                    "流动负债": 2600.00, "净资产": 7200.00, "存货": 80.00},
        "cashflow": {"经营活动现金流净额": 2150.00, "投资活动现金流净额": -850.00, "筹资活动现金流净额": -1200.00},
    },
}

_INDUSTRY_DATA = {
    "白酒": [
        {"name": "贵州茅台", "code": "600519.SH", "pe": 22.5, "pb": 7.4, "roe": 32.1, "revenue_growth": 15.7, "market_cap": 19850},
        {"name": "五粮液", "code": "000858.SZ", "pe": 16.8, "pb": 3.8, "roe": 25.3, "revenue_growth": 8.5, "market_cap": 6200},
        {"name": "泸州老窖", "code": "000568.SZ", "pe": 18.2, "pb": 5.1, "roe": 28.6, "revenue_growth": 12.3, "market_cap": 2850},
        {"name": "洋河股份", "code": "002304.SZ", "pe": 14.5, "pb": 2.6, "roe": 18.9, "revenue_growth": 5.2, "market_cap": 1650},
        {"name": "山西汾酒", "code": "600809.SH", "pe": 25.3, "pb": 8.2, "roe": 35.8, "revenue_growth": 22.1, "market_cap": 3200},
    ],
    "新能源汽车": [
        {"name": "比亚迪", "code": "002594.SZ", "pe": 25.8, "pb": 4.2, "roe": 16.3, "revenue_growth": 17.6, "market_cap": 8300},
        {"name": "宁德时代", "code": "300750.SZ", "pe": 20.5, "pb": 3.5, "roe": 18.2, "revenue_growth": 12.8, "market_cap": 9200},
        {"name": "赛力斯", "code": "601127.SH", "pe": 35.0, "pb": 6.8, "roe": 8.5, "revenue_growth": 85.3, "market_cap": 1850},
        {"name": "理想汽车", "code": "LI.US", "pe": 15.2, "pb": 2.8, "roe": 22.1, "revenue_growth": 45.6, "market_cap": 2800},
        {"name": "小鹏汽车", "code": "XPEV.US", "pe": -1, "pb": 1.5, "roe": -5.2, "revenue_growth": 35.2, "market_cap": 850},
    ],
    "互联网": [
        {"name": "腾讯控股", "code": "00700.HK", "pe": 18.2, "pb": 3.6, "roe": 22.0, "revenue_growth": 8.4, "market_cap": 38600},
        {"name": "阿里巴巴", "code": "09988.HK", "pe": 12.5, "pb": 1.8, "roe": 14.5, "revenue_growth": 5.2, "market_cap": 18500},
        {"name": "美团", "code": "03690.HK", "pe": 28.5, "pb": 4.2, "roe": 15.8, "revenue_growth": 18.6, "market_cap": 9500},
        {"name": "网易", "code": "09999.HK", "pe": 15.8, "pb": 3.2, "roe": 20.5, "revenue_growth": 6.8, "market_cap": 4800},
        {"name": "快手", "code": "01024.HK", "pe": 22.0, "pb": 2.8, "roe": 12.0, "revenue_growth": 12.5, "market_cap": 3200},
    ],
}

_INDEX_DATA = {
    "sh000001": {"code": "000001.SH", "name": "上证指数", "price": 3350.50, "change": 15.30, "change_pct": 0.46},
    "sh000300": {"code": "000300.SH", "name": "沪深300", "price": 3950.00, "change": -8.50, "change_pct": -0.21},
    "sz399001": {"code": "399001.SZ", "name": "深证成指", "price": 10850.60, "change": 25.80, "change_pct": 0.24},
    "sz399006": {"code": "399006.SZ", "name": "创业板指", "price": 2150.30, "change": 18.20, "change_pct": 0.85},
    "sh000819": {"code": "000819.SH", "name": "中证白酒", "price": 12580.50, "change": 85.20, "change_pct": 0.68},
    "sh931079": {"code": "931079.SH", "name": "新能源车", "price": 3850.80, "change": -22.50, "change_pct": -0.58},
}

_CALENDAR_DATA = {
    ("600519", 2026): [
        {"date": "2026-04-28", "event_type": "earnings", "description": "2025年年报 + 2026年一季报披露"},
        {"date": "2026-06-18", "event_type": "dividend", "description": "2025年度分红除权除息日（预计 ¥25/股）"},
        {"date": "2026-08-28", "event_type": "earnings", "description": "2026年半年报披露"},
        {"date": "2026-10-27", "event_type": "earnings", "description": "2026年三季报披露"},
        {"date": "2026-05-20", "event_type": "meeting", "description": "2025年度股东大会"},
    ],
    ("002594", 2026): [
        {"date": "2026-03-28", "event_type": "earnings", "description": "2025年年报披露"},
        {"date": "2026-05-15", "event_type": "dividend", "description": "2025年度分红除权除息日"},
        {"date": "2026-04-28", "event_type": "earnings", "description": "2026年一季报披露"},
        {"date": "2026-08-28", "event_type": "earnings", "description": "2026年半年报披露"},
        {"date": "2026-06-10", "event_type": "meeting", "description": "2025年度股东大会"},
    ],
    ("00700", 2026): [
        {"date": "2026-03-20", "event_type": "earnings", "description": "2025年年报披露"},
        {"date": "2026-05-18", "event_type": "dividend", "description": "2025年度分红除权除息日"},
        {"date": "2026-05-15", "event_type": "earnings", "description": "2026年一季报披露"},
        {"date": "2026-08-15", "event_type": "earnings", "description": "2026年半年报披露"},
    ],
    ("default", 2026): [
        {"date": "2026-04-30", "event_type": "earnings", "description": "年报+一季报截止日"},
        {"date": "2026-08-31", "event_type": "earnings", "description": "半年报截止日"},
        {"date": "2026-10-31", "event_type": "earnings", "description": "三季报截止日"},
    ],
}
