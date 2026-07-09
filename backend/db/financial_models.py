"""
财务数据库模型 — 结构化存储上市公司财务指标

V8.0 核心设计：SQL 优先查数字，RAG 辅助解读文本。

表结构:
  companies       — 公司基本信息（代码/名称/行业）
  financial_data  — 财务指标（EAV 模式，灵活扩展）
  standard_metrics — 标准指标定义

EAV 模式优势：
  - 不同公司可上报不同指标，不需要 alter table
  - 新增指标只需 INSERT 到 standard_metrics
  - 查询性能：UNIQUE(symbol, year, quarter, metric_name) + 索引
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, UniqueConstraint, Index, ForeignKey,
)
from sqlalchemy.orm import relationship
from .database import Base


class Company(Base):
    """上市公司基本信息"""
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, comment="股票代码（600519/002594等）")
    name = Column(String(100), nullable=False, comment="公司名称")
    market = Column(String(10), default="SH", comment="交易所：SH/SZ/HK")
    sector = Column(String(50), default="", comment="行业分类")
    listed_date = Column(String(20), default="", comment="上市日期")
    created_at = Column(DateTime, default=datetime.now)

    # 反向引用
    financials = relationship("FinancialData", back_populates="company", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "sector": self.sector,
        }


class StandardMetric(Base):
    """标准财务指标定义"""
    __tablename__ = "standard_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_key = Column(String(100), nullable=False, unique=True, comment="指标英文键名（revenue/net_profit等）")
    metric_name = Column(String(100), nullable=False, comment="中文名称（营业收入/净利润等）")
    category = Column(String(50), default="", comment="分类：income/balance/cashflow/ratio")
    unit = Column(String(20), default="元", comment="单位：元/万元/亿元/%")
    description = Column(String(500), default="")

    def to_dict(self):
        return {
            "metric_key": self.metric_key,
            "metric_name": self.metric_name,
            "category": self.category,
            "unit": self.unit,
        }


class FinancialData(Base):
    """
    财务指标数据（EAV 模式）

    每条记录 = 一家公司 + 一个报告期 + 一个指标 + 一个值
    唯一约束：同公司同年同季度同指标只有一条记录
    """
    __tablename__ = "financial_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(20), nullable=False, comment="股票代码（冗余，加速查询）")
    year = Column(Integer, nullable=False, comment="财年（2024）")
    quarter = Column(String(10), default="Q4", comment="季度：Q1/Q2/Q3/Q4/annual")
    metric_key = Column(String(100), nullable=False, comment="指标键名")
    metric_value = Column(Float, nullable=True, comment="指标数值")
    report_date = Column(String(20), default="", comment="报告日期（2024-12-31）")
    source = Column(String(50), default="AKShare", comment="数据来源")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    company = relationship("Company", back_populates="financials")

    # 唯一约束 + 索引
    __table_args__ = (
        UniqueConstraint("symbol", "year", "quarter", "metric_key", name="uq_financial_data"),
        Index("idx_financial_symbol", "symbol"),
        Index("idx_financial_metric", "metric_key"),
        Index("idx_financial_year", "year"),
    )

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "year": self.year,
            "quarter": self.quarter,
            "metric_key": self.metric_key,
            "metric_value": self.metric_value,
        }
