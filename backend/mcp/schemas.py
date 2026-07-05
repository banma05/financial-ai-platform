"""
MCP 模块数据模型 — Pydantic v2

定义 6 个 MCP 工具的请求参数和返回结构。
所有模型带 docstring 描述，供 Agent 的 LLM 理解工具能力。
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# ==================== Stock Price ====================

class StockPriceRequest(BaseModel):
    """股票行情查询请求"""
    symbol: str = Field(
        ..., description="股票代码，如 600519（贵州茅台）、002594（比亚迪）、00700（腾讯）"
    )
    period: Literal["realtime", "daily", "weekly", "monthly"] = Field(
        default="realtime", description="数据周期：realtime=实时, daily=日K, weekly=周K, monthly=月K"
    )


class StockPriceResponse(BaseModel):
    """股票行情返回"""
    symbol: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    price: float = Field(..., description="最新价（元/港元）")
    change: float = Field(..., description="涨跌额")
    change_pct: float = Field(..., description="涨跌幅 %")
    volume: int = Field(default=0, description="成交量（股）")
    market_cap: float = Field(default=0, description="总市值（亿元/亿港元）")
    pe_ttm: float = Field(default=0, description="市盈率 TTM")
    pb: float = Field(default=0, description="市净率")
    high_52w: float = Field(default=0, description="52周最高价")
    low_52w: float = Field(default=0, description="52周最低价")
    history: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="历史K线数据（仅 period != realtime 时返回）"
    )


# ==================== Financial Statements ====================

class FinancialStatementsRequest(BaseModel):
    """财务报表查询请求"""
    symbol: str = Field(..., description="股票代码")
    statement_type: Literal["income", "balance", "cashflow", "all"] = Field(
        default="all", description="报表类型：income=利润表, balance=资产负债表, cashflow=现金流量表, all=全部"
    )
    period: Literal["annual", "quarterly"] = Field(
        default="annual", description="报告期：annual=年报, quarterly=季报"
    )


class FinancialStatementsResponse(BaseModel):
    """财务报表返回"""
    symbol: str = Field(..., description="股票代码")
    name: str = Field(..., description="公司名称")
    period: str = Field(default="annual", description="报告期")
    report_date: str = Field(default="", description="报告截止日 YYYY-MM-DD")
    income: Optional[Dict[str, Any]] = Field(
        default=None, description="利润表数据（营业收入/营业成本/净利润等，单位亿元）"
    )
    balance: Optional[Dict[str, Any]] = Field(
        default=None, description="资产负债表数据（总资产/总负债/净资产等，单位亿元）"
    )
    cashflow: Optional[Dict[str, Any]] = Field(
        default=None, description="现金流量表数据（经营/投资/筹资活动现金流，单位亿元）"
    )


# ==================== Calculate Ratio ====================

class CalculateRatioRequest(BaseModel):
    """财务比率计算请求"""
    symbol: str = Field(..., description="股票代码")
    ratios: Optional[List[str]] = Field(
        default=None,
        description="需要计算的比率列表: roe, roa, gross_margin, net_margin, debt_ratio, "
                    "current_ratio, quick_ratio, interest_coverage, pe_ratio, pb_ratio, "
                    "revenue_growth, net_profit_growth, fcf, cf_to_net_profit, dupont。"
                    "不传则计算全部 15 个"
    )
    year: Optional[int] = Field(default=None, description="年份，不传则用最新年报数据")


class RatioResult(BaseModel):
    """单个比率计算结果"""
    name: str = Field(..., description="比率英文名")
    display_name: str = Field(..., description="比率中文名")
    value: float = Field(..., description="计算结果")
    unit: str = Field(default="%", description="单位（% / 倍 / 亿元）")
    formula: str = Field(default="", description="计算公式")
    interpretation: str = Field(default="", description="简要解读")


class CalculateRatioResponse(BaseModel):
    """财务比率计算返回"""
    symbol: str = Field(..., description="股票代码")
    name: str = Field(..., description="公司名称")
    ratios: List[RatioResult] = Field(default_factory=list, description="比率计算结果列表")


# ==================== Industry Comparison ====================

class IndustryComparisonRequest(BaseModel):
    """行业对比查询请求"""
    symbol: str = Field(..., description="标的代码（用于确定行业），如 600519 → 白酒行业")
    metrics: Optional[List[str]] = Field(
        default=None, description="对比指标: pe, pb, roe, revenue_growth, market_cap。不传则全部"
    )


class PeerInfo(BaseModel):
    """同行业公司信息"""
    name: str = Field(..., description="公司名称")
    code: str = Field(..., description="股票代码")


class IndustryComparisonResponse(BaseModel):
    """行业对比返回"""
    sector: str = Field(..., description="行业名称")
    metrics: List[str] = Field(default_factory=list, description="对比指标列表")
    target: Optional[Dict[str, Any]] = Field(default=None, description="目标公司数据")
    peers: List[Dict[str, Any]] = Field(default_factory=list, description="同行业公司对比数据")
    peer_count: int = Field(default=0, description="可比公司数量")


# ==================== Market Index ====================

class MarketIndexRequest(BaseModel):
    """市场指数查询请求"""
    index: str = Field(
        default="sh000001",
        description="指数代码: sh000001(上证), sh000300(沪深300), sz399001(深证), "
                    "sz399006(创业板), sh000819(中证白酒), sh931079(新能源车)"
    )


class MarketIndexResponse(BaseModel):
    """市场指数返回"""
    code: str = Field(..., description="指数代码")
    name: str = Field(..., description="指数名称")
    price: float = Field(..., description="当前点位")
    change: float = Field(..., description="涨跌点")
    change_pct: float = Field(..., description="涨跌幅 %")


# ==================== Financial Calendar ====================

class FinancialCalendarRequest(BaseModel):
    """财报日历查询请求"""
    symbol: str = Field(..., description="股票代码")
    year: int = Field(default=2026, description="年份")


class CalendarEvent(BaseModel):
    """日历事件"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    event_type: str = Field(..., description="事件类型: earnings/dividend/meeting")
    description: str = Field(..., description="事件描述")


class FinancialCalendarResponse(BaseModel):
    """财报日历返回"""
    symbol: str = Field(..., description="股票代码")
    name: str = Field(..., description="公司名称")
    year: int = Field(..., description="年份")
    events: List[CalendarEvent] = Field(default_factory=list, description="事件列表")
    event_count: int = Field(default=0, description="事件数量")
