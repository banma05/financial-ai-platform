"""
结构化查询服务 — SQL 优先的数据获取层

StructuredDataService 是核心服务：
1. try_query(query) → 尝试用 SQL 回答查询
   - 成功：返回 DataQueryTool 兼容格式
   - 无法处理：返回 None，调用方走 RAG 兜底

Query 解析策略（零 LLM）：
  - 公司名：复用 entity_router.detect_company_entities()
  - 年份：正则提取 2024年 / 2022-2024年 / 去年
  - 指标：匹配 STANDARD_METRICS 已知指标列表
  - 无法解析 → 返回 None
"""
import re
import os
from typing import Optional, List, Dict, Tuple
from loguru import logger

from db import SessionLocal
from data_layer.models import Company, FinancialData, STANDARD_METRICS

# ── 指标关键词 → 标准指标名映射（支持简短写法）──
METRIC_ALIASES: Dict[str, str] = {
    # 利润表简短写法
    "营收": "营业收入",
    "营业总收入": "营业收入",
    "收入": "营业收入",
    "成本": "营业成本",
    "净利": "净利润",
    "归母净利润": "净利润",
    "毛利": "毛利润",
    "EBIT": "EBIT",
    "息税前利润": "EBIT",
    "每股收益": "基本每股收益",
    "EPS": "基本每股收益",
    "研发投入": "研发费用",
    # 资产负债表简短写法
    "资产总计": "总资产",
    "负债合计": "总负债",
    "负债": "总负债",
    "权益": "净资产",
    "股东权益": "净资产",
    "存货净额": "存货",
    # 现金流简短写法
    "经营现金流": "经营活动产生的现金流量净额",
    "经营活动现金流": "经营活动产生的现金流量净额",
    "投资现金流": "投资活动产生的现金流量净额",
    "投资活动现金流": "投资活动产生的现金流量净额",
    "筹资现金流": "筹资活动产生的现金流量净额",
    "筹资活动现金流": "筹资活动产生的现金流量净额",
    "FCF": "资本支出",
    "自由现金流": "资本支出",
    # 派生指标
    "毛利率": "毛利率",
    "净利率": "净利率",
    "资产负债率": "资产负债率",
    "ROE": "净资产",
    "ROA": "总资产",
}

# ── 跨文档对比关键词（这些 query 不适合 SQL 单公司查询）──
CROSS_COMPANY_KEYWORDS = ["对比", "比较", "差异", "vs", "VS", "两家", "三家", "哪个更"]


class StructuredDataService:
    """
    结构化数据查询服务。

    用法:
        service = StructuredDataService()
        result = service.try_query("贵州茅台 2024年 营业收入 营业成本")
        if result:
            return result  # SQL 命中
        else:
            return rag_fallback(query)  # 走 RAG
    """

    def __init__(self):
        self._company_cache: Optional[Dict[str, int]] = None  # {标准名: id}

    # ========== 公共入口 ==========

    def try_query(self, query: str) -> Optional[dict]:
        """
        尝试用结构化数据回答查询。

        返回 DataQueryTool 兼容格式，无法处理时返回 None。

        返回格式:
            {
                "found": True/False,
                "data": {"营业收入": 1709.90, "营业成本": 89.34, ...},
                "summary": "从结构化数据库查询到 贵州茅台 2024年 5个指标",
                "raw_chunks": [],
                "confidence": 0.95,
                "source": "structured_db",
            }
        """
        try:
            # Step 1: 解析 query
            parsed = self._parse_query(query)
            if not parsed:
                return None

            company_name, years, metrics = parsed
            logger.debug(f"[SQL] 解析: company={company_name}, years={years}, metrics={metrics}")

            # Step 2: 查公司 ID
            company_id = self._resolve_company(company_name)
            if not company_id:
                logger.debug(f"[SQL] 未找到公司: {company_name}")
                return None

            # Step 3: SQL 查询
            rows = self._query_metrics(company_id, years, metrics)
            if not rows:
                logger.debug(f"[SQL] 无数据: {company_name} {years} {metrics}")
                return None

            # Step 4: 检查完整性（所有请求指标都有数据）
            found_metrics = set(r.metric_name for r in rows)
            missing = [m for m in metrics if m not in found_metrics]
            if missing:
                logger.debug(f"[SQL] 缺失指标: {missing}，走 RAG 兜底")
                return None

            # Step 5: 格式化返回
            return self._format_result(company_name, years, rows, metrics)

        except Exception as e:
            logger.warning(f"[SQL] 查询降级（静默）: {e}")
            return None

    # ========== Query 解析 ==========

    def _parse_query(self, query: str) -> Optional[Tuple[str, List[int], List[str]]]:
        """
        零 LLM 解析器：从 query 中提取 (公司名, 年份列表, 指标列表)。

        返回 None 表示无法解析（走 RAG 兜底）。
        """
        # ── 快速拒绝：跨文档对比查询 ──
        if any(kw in query for kw in CROSS_COMPANY_KEYWORDS):
            logger.debug(f"[SQL] 跨文档对比查询，走 RAG: {query[:50]}")
            return None

        # ── 提取公司名 ──
        company = self._detect_company(query)
        if not company:
            logger.debug(f"[SQL] 未检测到公司名: {query[:50]}")
            return None

        # ── 提取年份 ──
        years = self._detect_years(query)
        # 无年份默认最近一年（在查询时处理）

        # ── 提取指标 ──
        metrics = self._detect_metrics(query)
        if not metrics:
            logger.debug(f"[SQL] 未检测到已知指标: {query[:50]}")
            return None

        return company, years, metrics

    def _detect_company(self, query: str) -> Optional[str]:
        """
        从 query 中识别公司名。

        使用 entity_router 做实体检测，回退到 Company 表的别名匹配。
        """
        # ── Level 1: entity_router ──
        try:
            from rag.entity_router import detect_company_entities
            entities = detect_company_entities(query)
            if entities:
                # 映射注册名 → Company 标准名
                entity_to_standard = {
                    "贵州茅台": "贵州茅台",
                    "比亚迪": "比亚迪",
                    "腾讯": "腾讯控股",
                }
                for ent in entities:
                    if ent in entity_to_standard:
                        return entity_to_standard[ent]
                    return ent  # 直接用注册名
        except Exception:
            pass

        # ── Level 2: Company 表别名匹配 ──
        companies = self._load_companies()
        for std_name, cid in companies.items():
            if std_name in query:
                return std_name
            # 也检查别名
            aliases = self._get_company_aliases(std_name)
            for alias in aliases:
                if alias in query:
                    return std_name

        return None

    def _detect_years(self, query: str) -> List[int]:
        """
        从 query 中提取年份。

        支持格式：
        - "2024年" → [2024]
        - "2022-2024年" / "2022年到2024年" → [2022, 2023, 2024]
        - "近三年" → 默认 []（SQL 查最近三年）
        - "去年" → 默认 []（SQL 查最近两年）
        """
        years = set()

        # 范围格式: 2022-2024 或 2022年到2024年
        range_match = re.findall(r'(\d{4})\s*(?:年|到|至|-)\s*(\d{4})\s*年?', query)
        for start, end in range_match:
            start_y, end_y = int(start), int(end)
            years.update(range(start_y, end_y + 1))

        # 单年格式: 2024年
        single_match = re.findall(r'(\d{4})\s*年', query)
        for y in single_match:
            years.add(int(y))

        # 相对年份
        if "去年" in query or "上年" in query:
            # 不限定具体年份，在 SQL 查询时查最近 2 年
            return []

        return sorted(years) if years else []

    def _detect_metrics(self, query: str) -> List[str]:
        """
        从 query 中匹配已知指标名。

        策略：遍历 STANDARD_METRICS + METRIC_ALIASES，
        匹配 query 中包含的指标关键词。
        """
        found = []
        # 先检查完整标准名
        for metric in STANDARD_METRICS:
            if metric in query and metric not in found:
                found.append(metric)

        # 再检查别名（短写法）
        for alias, standard in METRIC_ALIASES.items():
            if alias in query and standard not in found:
                found.append(standard)

        # 去重并保持顺序
        return list(dict.fromkeys(found))

    # ========== 公司管理 ==========

    def _load_companies(self) -> Dict[str, int]:
        """加载公司注册表到内存缓存（懒加载）"""
        if self._company_cache is not None:
            return self._company_cache

        db = SessionLocal()
        try:
            companies = db.query(Company).all()
            self._company_cache = {c.name: c.id for c in companies}
            # 确保种子公司存在
            self._ensure_seed_companies(db)
        except Exception:
            self._company_cache = {}
        finally:
            db.close()
        return self._company_cache

    def _ensure_seed_companies(self, db):
        """确保基础公司数据存在（首次运行时插入种子数据）"""
        seed = [
            ("贵州茅台", ["茅台", "贵州茅台", "600519"], "白酒"),
            ("比亚迪", ["比亚迪", "BYD", "002594"], "新能源"),
            ("腾讯控股", ["腾讯", "腾讯控股", "Tencent", "0700.HK"], "互联网"),
            ("五粮液", ["五粮液"], "白酒"),
            ("宁德时代", ["宁德时代", "宁德"], "新能源"),
        ]
        for name, aliases, industry in seed:
            if not db.query(Company).filter_by(name=name).first():
                db.add(Company(name=name, aliases=aliases, industry=industry))
        db.commit()

    def _resolve_company(self, name: str) -> Optional[int]:
        """根据公司名/别名查 ID"""
        companies = self._load_companies()
        if name in companies:
            return companies[name]
        # 别名匹配
        for std_name, cid in companies.items():
            aliases = self._get_company_aliases(std_name)
            if name in aliases:
                return cid
        return None

    def _get_company_aliases(self, name: str) -> List[str]:
        """获取公司的别名列表"""
        db = SessionLocal()
        try:
            c = db.query(Company).filter_by(name=name).first()
            return c.aliases if c else []
        except Exception:
            return []
        finally:
            db.close()

    # ========== SQL 查询 ==========

    def _query_metrics(self, company_id: int, years: List[int],
                        metrics: List[str]) -> List[FinancialData]:
        """从 FinancialData 表中查询指标值"""
        db = SessionLocal()
        try:
            q = db.query(FinancialData).filter(
                FinancialData.company_id == company_id,
                FinancialData.metric_name.in_(metrics),
            )
            if years:
                q = q.filter(FinancialData.year.in_(years))
            else:
                # 无年份指定：取最近一年数据
                q = q.order_by(FinancialData.year.desc())

            return q.all()
        except Exception as e:
            logger.warning(f"[SQL] 查询失败: {e}")
            return []
        finally:
            db.close()

    # ========== 结果格式化 ==========

    def _format_result(self, company_name: str, years: List[int],
                        rows: List[FinancialData], metrics: List[str]) -> dict:
        """格式化 SQL 查询结果为 DataQueryTool 兼容格式"""

        # 扁平的指标名→值映射
        data = {}
        has_multi_year = len(set(r.year for r in rows)) > 1

        for r in rows:
            if has_multi_year:
                # 多年：用 "指标名_年份" 格式
                data[f"{r.metric_name}_{r.year}"] = r.value
            else:
                # 单年：直接用指标名
                data[r.metric_name] = r.value

        # 多年时自动注入增长率参数
        if has_multi_year and len(rows) >= 2:
            self._inject_growth_params(data, rows)

        # 构建摘要
        year_str = f"{years[0]}年" if years else ""
        summary = f"从结构化数据库查询到 {company_name} {year_str} {len(data)}个指标"

        return {
            "found": True,
            "data": data,
            "summary": summary,
            "raw_chunks": [],
            "confidence": 0.95,
            "source": "structured_db",
        }

    @staticmethod
    def _inject_growth_params(data: dict, rows: List[FinancialData]):
        """
        多年数据时自动注入 current/previous 参数，供 growth 公式使用。

        例如: 营业收入_2024 + 营业收入_2023
        → data["current_revenue"] = 营业收入_2024
        → data["previous_revenue"] = 营业收入_2023
        """
        # 按指标名和年份分组
        by_metric: Dict[str, Dict[int, float]] = {}
        for r in rows:
            by_metric.setdefault(r.metric_name, {})[r.year] = r.value

        # 增长率映射
        growth_map = {
            "营业收入": ("current_revenue", "previous_revenue"),
            "净利润": ("current_profit", "previous_profit"),
        }

        for metric, (curr_key, prev_key) in growth_map.items():
            yearly = by_metric.get(metric, {})
            if len(yearly) >= 2:
                sorted_years = sorted(yearly.keys(), reverse=True)
                data[curr_key] = yearly[sorted_years[0]]
                data[prev_key] = yearly[sorted_years[1]]

    # ========== 工具方法 ==========

    def invalidate_cache(self):
        """清空公司缓存（种子数据变更后调用）"""
        self._company_cache = None

    def get_stats(self) -> dict:
        """获取结构化数据层的统计信息"""
        db = SessionLocal()
        try:
            companies = db.query(Company).count()
            data_count = db.query(FinancialData).count()
            from sqlalchemy import func
            year_range = db.query(
                func.min(FinancialData.year),
                func.max(FinancialData.year),
            ).first()
            return {
                "companies": companies,
                "total_metrics": data_count,
                "year_range": f"{year_range[0]}-{year_range[1]}" if year_range[0] else "无数据",
            }
        except Exception:
            return {"companies": 0, "total_metrics": 0, "year_range": "错误"}
        finally:
            db.close()


# ==================== 全局单例 ====================

_service_instance: Optional[StructuredDataService] = None


def get_service() -> StructuredDataService:
    """获取全局 StructuredDataService 实例（懒加载）"""
    global _service_instance
    if _service_instance is None:
        _service_instance = StructuredDataService()
    return _service_instance
