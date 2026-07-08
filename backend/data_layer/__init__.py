"""
结构化数据层 — SQL 优先查询 + 数据填充

对外暴露：
  StructuredDataService  — 核心查询服务（SQL优先）
  DataPopulator         — 数据填充工具
  Company, FinancialData — ORM 模型
"""
from .models import Company, FinancialData, STANDARD_METRICS
from .service import StructuredDataService, get_service
from .populator import DataPopulator

__all__ = [
    "Company",
    "FinancialData",
    "STANDARD_METRICS",
    "StructuredDataService",
    "get_service",
    "DataPopulator",
]
