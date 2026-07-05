"""
MCP Mock 数据生成器 — 开发/演示用

覆盖 3 家核心标的完整数据：
- 贵州茅台 (600519.SH) — 白酒龙头
- 比亚迪 (002594.SZ)   — 新能源车龙头
- 腾讯控股 (00700.HK)  — 互联网龙头

数据来源：2024年年报公开数据 + 合理估算的实时行情
所有真 API 调用预留统一接口，替换 Mock 时只需改此文件。
"""

from typing import Dict, List, Optional, Any
from datetime import date, timedelta

# ==================== 标的索引 ====================

SYMBOLS = {
    "600519": "贵州茅台",
    "600519.SH": "贵州茅台",
    "002594": "比亚迪",
    "002594.SZ": "比亚迪",
    "00700": "腾讯控股",
    "00700.HK": "腾讯控股",
}

SECTORS = {
    "600519": "白酒",
    "002594": "新能源汽车",
    "00700": "互联网",
}

# ==================== 1. 股票行情 Mock ====================

def get_stock_price(symbol: str, period: str = "realtime") -> Dict[str, Any]:
    """
    获取股票行情数据。

    参数:
        symbol: 股票代码 (600519 / 002594 / 00700)
        period: "realtime"(实时) / "daily"(日K) / "weekly"(周K) / "monthly"(月K)

    返回:
        {
            "symbol", "name", "price", "change", "change_pct",
            "volume", "market_cap", "pe_ttm", "pb", "high_52w", "low_52w",
            "history": [...]  # period != "realtime" 时附带
        }
    """
    data = _PRICE_DATA.get(_normalize(symbol))
    if not data:
        return {"error": f"未找到标的: {symbol}", "available": list(SYMBOLS.keys())}

    result = {
        "symbol": data["symbol"],
        "name": data["name"],
        "price": data["price"],
        "change": data["change"],
        "change_pct": data["change_pct"],
        "volume": data["volume"],
        "market_cap": data["market_cap"],
        "pe_ttm": data["pe_ttm"],
        "pb": data["pb"],
        "high_52w": data["high_52w"],
        "low_52w": data["low_52w"],
    }

    if period != "realtime":
        result["history"] = _generate_history(data["price"], period)

    return result


def _normalize(symbol: str) -> str:
    """统一代码格式"""
    return symbol.replace(".SH", "").replace(".SZ", "").replace(".HK", "")


_PRICE_DATA = {
    "600519": {
        "symbol": "600519.SH", "name": "贵州茅台",
        "price": 1580.50, "change": 12.30, "change_pct": 0.78,
        "volume": 3820000, "market_cap": 19850.0,  # 亿
        "pe_ttm": 22.5, "pb": 7.4,
        "high_52w": 1850.0, "low_52w": 1350.0,
    },
    "002594": {
        "symbol": "002594.SZ", "name": "比亚迪",
        "price": 285.60, "change": -3.20, "change_pct": -1.11,
        "volume": 12500000, "market_cap": 8300.0,
        "pe_ttm": 25.8, "pb": 4.2,
        "high_52w": 350.0, "low_52w": 220.0,
    },
    "00700": {
        "symbol": "00700.HK", "name": "腾讯控股",
        "price": 420.0, "change": 5.0, "change_pct": 1.20,
        "volume": 9800000, "market_cap": 38600.0,  # 港元
        "pe_ttm": 18.2, "pb": 3.6,
        "high_52w": 480.0, "low_52w": 310.0,
    },
}


def _generate_history(price: float, period: str) -> List[Dict]:
    """生成模拟历史K线数据"""
    import random
    random.seed(hash(price))  # 固定种子保证可复现
    days = {"daily": 30, "weekly": 12, "monthly": 24}.get(period, 30)
    today = date.today()
    result = []
    for i in range(days, 0, -1):
        d = today - timedelta(days=i if period == "daily" else i * 7)
        change_pct = random.uniform(-3, 3)
        close = round(price * (1 + sum(random.uniform(-1, 1) for _ in range(i)) * 0.02), 2)
        result.append({
            "date": d.isoformat(),
            "close": max(close, 1),
            "change_pct": round(change_pct, 2),
        })
    return result


# ==================== 2. 财务报表 Mock ====================

def get_financial_statements(
    symbol: str,
    statement_type: str = "all",
    period: str = "annual",
) -> Dict[str, Any]:
    """
    获取财务报表数据。

    参数:
        symbol: 股票代码
        statement_type: "income"(利润表) / "balance"(资产负债表) / "cashflow"(现金流) / "all"(全部)
        period: "annual"(年报) / "quarterly"(季报)

    返回:
        {
            "symbol", "name", "period", "report_date",
            "income": {...},    # statement_type in ("income", "all")
            "balance": {...},   # statement_type in ("balance", "all")
            "cashflow": {...},  # statement_type in ("cashflow", "all")
        }
    """
    norm = _normalize(symbol)
    all_data = _STATEMENT_DATA.get(norm)
    if not all_data:
        return {"error": f"未找到标的: {symbol}"}

    result = {
        "symbol": all_data["symbol"], "name": all_data["name"],
        "period": period, "report_date": all_data["report_date"],
    }
    if statement_type in ("income", "all"):
        result["income"] = all_data["income"]
    if statement_type in ("balance", "all"):
        result["balance"] = all_data["balance"]
    if statement_type in ("cashflow", "all"):
        result["cashflow"] = all_data["cashflow"]
    return result


_STATEMENT_DATA = {
    "600519": {
        "symbol": "600519.SH", "name": "贵州茅台", "report_date": "2024-12-31",
        "income": {
            "营业收入": 1741.44, "营业成本": 132.64,
            "销售费用": 58.15, "管理费用": 85.30, "研发费用": 1.72,
            "财务费用": -25.80,  # 利息收入 > 利息支出
            "营业利润": 1435.92, "净利润": 862.28,
            "营业收入_上期": 1505.60, "净利润_上期": 747.34,
        },
        "balance": {
            "总资产": 3120.00, "流动资产": 2350.00,
            "总负债": 432.55, "流动负债": 368.20,
            "净资产": 2687.45, "存货": 450.30,
        },
        "cashflow": {
            "经营活动现金流净额": 665.80,
            "投资活动现金流净额": -120.50,
            "筹资活动现金流净额": -585.30,  # 大额分红
        },
    },
    "002594": {
        "symbol": "002594.SZ", "name": "比亚迪", "report_date": "2024-12-31",
        "income": {
            "营业收入": 6023.15, "营业成本": 4800.50,
            "销售费用": 245.00, "管理费用": 180.30, "研发费用": 186.50,
            "财务费用": 58.20,
            "营业利润": 468.50, "净利润": 321.70,
            "营业收入_上期": 5120.00, "净利润_上期": 280.30,
        },
        "balance": {
            "总资产": 5234.00, "流动资产": 2850.00,
            "总负债": 3256.00, "流动负债": 2680.00,
            "净资产": 1978.00, "存货": 680.50,
        },
        "cashflow": {
            "经营活动现金流净额": 850.30,
            "投资活动现金流净额": -720.00,  # 扩产投资
            "筹资活动现金流净额": 120.50,
        },
    },
    "00700": {
        "symbol": "00700.HK", "name": "腾讯控股", "report_date": "2024-12-31",
        "income": {
            "营业收入": 6600.00, "营业成本": 3500.00,
            "销售费用": 420.00, "管理费用": 850.00, "研发费用": 520.00,
            "财务费用": 80.00,
            "营业利润": 1950.00, "净利润": 1580.00,
            "营业收入_上期": 6090.00, "净利润_上期": 1420.00,
        },
        "balance": {
            "总资产": 12000.00, "流动资产": 4800.00,
            "总负债": 4800.00, "流动负债": 2600.00,
            "净资产": 7200.00, "存货": 80.00,
        },
        "cashflow": {
            "经营活动现金流净额": 2150.00,
            "投资活动现金流净额": -850.00,
            "筹资活动现金流净额": -1200.00,  # 回购+分红
        },
    },
}


# ==================== 3. 行业对比 Mock ====================

def get_industry_comparison(
    symbol: str,
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    获取同行业可比公司数据对比。

    参数:
        symbol: 标的代码（用于确定行业）
        metrics: 关注的指标列表，默认全部

    返回:
        {"sector": "白酒", "peers": [...], "target": {...}}
    """
    norm = _normalize(symbol)
    sector = SECTORS.get(norm)
    if not sector:
        return {"error": f"未找到标的: {symbol}"}

    peers = _INDUSTRY_DATA.get(sector, [])
    if not metrics:
        metrics = ["pe", "pb", "roe", "revenue_growth"]

    target_name = SYMBOLS.get(norm, symbol)
    target_peer = next((p for p in peers if p["name"] == target_name), None)

    # 筛选指标
    result_peers = []
    for p in peers:
        filtered = {k: v for k, v in p.items() if k in metrics or k in ("name", "code")}
        result_peers.append(filtered)

    return {
        "sector": sector,
        "metrics": metrics,
        "target": {k: v for k, v in (target_peer or {}).items() if k in metrics or k in ("name", "code")},
        "peers": result_peers,
        "peer_count": len(result_peers),
    }


_INDUSTRY_DATA = {
    "白酒": [
        {"name": "贵州茅台", "code": "600519.SH", "pe": 22.5, "pb": 7.4,
         "roe": 32.1, "revenue_growth": 15.7, "market_cap": 19850},
        {"name": "五粮液", "code": "000858.SZ", "pe": 16.8, "pb": 3.8,
         "roe": 25.3, "revenue_growth": 8.5, "market_cap": 6200},
        {"name": "泸州老窖", "code": "000568.SZ", "pe": 18.2, "pb": 5.1,
         "roe": 28.6, "revenue_growth": 12.3, "market_cap": 2850},
        {"name": "洋河股份", "code": "002304.SZ", "pe": 14.5, "pb": 2.6,
         "roe": 18.9, "revenue_growth": 5.2, "market_cap": 1650},
        {"name": "山西汾酒", "code": "600809.SH", "pe": 25.3, "pb": 8.2,
         "roe": 35.8, "revenue_growth": 22.1, "market_cap": 3200},
    ],
    "新能源汽车": [
        {"name": "比亚迪", "code": "002594.SZ", "pe": 25.8, "pb": 4.2,
         "roe": 16.3, "revenue_growth": 17.6, "market_cap": 8300},
        {"name": "宁德时代", "code": "300750.SZ", "pe": 20.5, "pb": 3.5,
         "roe": 18.2, "revenue_growth": 12.8, "market_cap": 9200},
        {"name": "赛力斯", "code": "601127.SH", "pe": 35.0, "pb": 6.8,
         "roe": 8.5, "revenue_growth": 85.3, "market_cap": 1850},
        {"name": "理想汽车", "code": "LI.US", "pe": 15.2, "pb": 2.8,
         "roe": 22.1, "revenue_growth": 45.6, "market_cap": 2800},
        {"name": "小鹏汽车", "code": "XPEV.US", "pe": -1, "pb": 1.5,
         "roe": -5.2, "revenue_growth": 35.2, "market_cap": 850},
    ],
    "互联网": [
        {"name": "腾讯控股", "code": "00700.HK", "pe": 18.2, "pb": 3.6,
         "roe": 22.0, "revenue_growth": 8.4, "market_cap": 38600},
        {"name": "阿里巴巴", "code": "09988.HK", "pe": 12.5, "pb": 1.8,
         "roe": 14.5, "revenue_growth": 5.2, "market_cap": 18500},
        {"name": "美团", "code": "03690.HK", "pe": 28.5, "pb": 4.2,
         "roe": 15.8, "revenue_growth": 18.6, "market_cap": 9500},
        {"name": "网易", "code": "09999.HK", "pe": 15.8, "pb": 3.2,
         "roe": 20.5, "revenue_growth": 6.8, "market_cap": 4800},
        {"name": "快手", "code": "01024.HK", "pe": 22.0, "pb": 2.8,
         "roe": 12.0, "revenue_growth": 12.5, "market_cap": 3200},
    ],
}


# ==================== 4. 市场指数 Mock ====================

def get_market_index(index: str = "sh000001") -> Dict[str, Any]:
    """
    获取市场指数行情。

    参数:
        index: 指数代码
            sh000001 — 上证指数
            sh000300 — 沪深300
            sz399001 — 深证成指
            sz399006 — 创业板指
            sh000819 — 中证白酒
            sh931079 — 中证新能源汽车

    返回:
        {"code", "name", "price", "change", "change_pct", "volume"}
    """
    data = _INDEX_DATA.get(index)
    if not data:
        return {"error": f"未找到指数: {index}", "available": list(_INDEX_DATA.keys())}
    return dict(data)


_INDEX_DATA = {
    "sh000001": {"code": "000001.SH", "name": "上证指数",
                 "price": 3350.50, "change": 15.30, "change_pct": 0.46},
    "sh000300": {"code": "000300.SH", "name": "沪深300",
                 "price": 3950.00, "change": -8.50, "change_pct": -0.21},
    "sz399001": {"code": "399001.SZ", "name": "深证成指",
                 "price": 10850.60, "change": 25.80, "change_pct": 0.24},
    "sz399006": {"code": "399006.SZ", "name": "创业板指",
                 "price": 2150.30, "change": 18.20, "change_pct": 0.85},
    "sh000819": {"code": "000819.SH", "name": "中证白酒",
                 "price": 12580.50, "change": 85.20, "change_pct": 0.68},
    "sh931079": {"code": "931079.SH", "name": "中证新能源汽车",
                 "price": 3850.80, "change": -22.50, "change_pct": -0.58},
}


# ==================== 5. 财报日历 Mock ====================

def get_financial_calendar(symbol: str, year: int = 2026) -> Dict[str, Any]:
    """
    获取财务报表相关的重要日期。

    参数:
        symbol: 股票代码
        year: 年份

    返回:
        {"symbol", "name", "year", "events": [{date, event_type, description}, ...]}
    """
    norm = _normalize(symbol)
    name = SYMBOLS.get(norm, symbol)
    events = _CALENDAR_DATA.get((norm, year), _CALENDAR_DATA.get(("default", year), []))

    return {
        "symbol": symbol, "name": name, "year": year,
        "events": events, "event_count": len(events),
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
