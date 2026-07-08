"""
结构化财务数据模型 — SQLAlchemy ORM

两张表：
  data_companies          — 公司注册表（标准名+别名+行业）
  data_financial_data     — 财务指标 EAV 表（一行存一个指标值）

所有模型继承 db.database.Base，由 init_db() 自动建表。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, UniqueConstraint
from db.database import Base


# ==================== 公司注册表 ====================

class Company(Base):
    """可分析的公司实体，含标准名和别名列表"""

    __tablename__ = "data_companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, comment="公司标准名")
    aliases = Column(JSON, default=list, comment="别名列表，如 ['茅台','600519']")
    industry = Column(String(50), default="", comment="行业分类：白酒/新能源/互联网")
    created_at = Column(DateTime, default=datetime.now)

    def __repr__(self):
        return f"<Company {self.name}>"


# ==================== 财务指标 EAV 表 ====================

class FinancialData(Base):
    """
    财务指标实体-属性-值表。

    每行代表一个公司的某一年某个指标的值。
    UNIQUE(company_id, year, metric_name) 保证不重复。

    示例行：
      company_id=1, year=2024, metric_name="营业收入", value=1709.90, unit="亿元"
    """

    __tablename__ = "data_financial_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, nullable=False, index=True, comment="关联 Company.id")
    year = Column(Integer, nullable=False, index=True, comment="财年")
    metric_name = Column(String(100), nullable=False, comment="标准化中文指标名")
    value = Column(Float, nullable=False, comment="数值")
    unit = Column(String(20), default="亿元", comment="单位：亿元/万元/%/元/倍")

    source_document = Column(String(500), default="", comment="来源 PDF 文件名")
    confidence = Column(Float, default=0.0, comment="提取置信度 0-1")
    is_derived = Column(Integer, default=0, comment="0=直接提取, 1=计算派生（如毛利率）")

    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("company_id", "year", "metric_name",
                         name="uq_company_year_metric"),
    )

    def __repr__(self):
        return f"<FinancialData {self.company_id}/{self.year}/{self.metric_name}={self.value}{self.unit}>"


# ==================== 标准指标名清单 ====================

STANDARD_METRICS = [
    # ── 利润表 ──
    "营业收入",
    "营业成本",
    "净利润",
    "毛利润",
    "利息费用",
    "EBIT",
    "研发费用",
    "基本每股收益",
    # ── 资产负债表 ──
    "总资产",
    "总负债",
    "净资产",
    "流动资产",
    "流动负债",
    "存货",
    "期初总资产",
    "期初净资产",
    "期初流动资产",
    "期初流动负债",
    # ── 现金流 ──
    "经营活动产生的现金流量净额",
    "投资活动产生的现金流量净额",
    "筹资活动产生的现金流量净额",
    "资本支出",
    # ── 派生指标（population 时计算）──
    "毛利率",
    "净利率",
    "资产负债率",
]
