"""
结构化数据填充工具 — 从 PDF 年报中批量提取财务指标写入 SQL

用法:
    python -m data_layer.populator --all      # 批量回填所有已有文档
    python -m data_layer.populator --company "贵州茅台" --year 2024  # 单公司单年
"""
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from loguru import logger

from db import SessionLocal
from data_layer.models import Company, FinancialData, STANDARD_METRICS

# ── 提取 prompt 模板 — 一次调用提取全部标准指标 ──
BULK_EXTRACT_PROMPT = """你是一个精确的财务数据提取专家。请从以下文档片段中提取 {company} {year} 年的财务数据。

## 需要提取的指标（找不到则输出 null）

**利润表**：
营业收入, 营业成本, 净利润, 毛利润, 利息费用, EBIT, 研发费用, 基本每股收益

**资产负债表**：
总资产, 总负债, 净资产, 流动资产, 流动负债, 存货
期初总资产, 期初净资产

**现金流**：
经营活动产生的现金流量净额, 投资活动产生的现金流量净额,
筹资活动产生的现金流量净额, 资本支出

## 核心规则（违反即为错误）
1. **只输出一个 JSON 对象，不要任何额外文字、解释、代码块标记**
2. 数值必须是纯数字，严禁带单位（"亿元""万元""%""元"全部去掉）
3. 金额类统一转为「亿元」单位（万元÷10000，元÷100000000）
4. 百分比类直接输出数值：92.38 而非 "92.38%" 或 "0.9238"
5. 找不到的指标输出 null
6. 如果文档有期初/期末数据，分别填到期初和期末字段

## 文档片段
{context}

## 请输出（只输出 JSON，不要代码块标记）"""


class DataPopulator:
    """
    从 PDF 文档提取结构化财务数据并写入 SQL。

    流程：
    1. 识别文档对应的公司和年份
    2. 通过 RAG 检索该文档中财务相关段落
    3. LLM 一次批量提取全部标准指标
    4. 去重写入 FinancialData 表
    5. 计算派生指标（毛利率、净利率、资产负债率）
    """

    def __init__(self):
        pass

    # ========== 公共 API ==========

    def populate_company(self, company_name: str, year: int) -> int:
        """
        为指定公司+年份提取并存储财务数据。

        返回成功写入的指标数。
        """
        logger.info(f"[Populator] 开始填充: {company_name} {year}")

        # Step 1: 确保公司注册
        company_id = self._ensure_company(company_name)

        # Step 2: RAG 检索该公司+年份的 chunks
        chunks = self._retrieve_chunks(company_name, year)
        if not chunks:
            logger.warning(f"[Populator] 无检索结果: {company_name} {year}")
            return 0

        # Step 3: LLM 批量提取
        extracted = self._extract_metrics(company_name, year, chunks)
        if not extracted:
            logger.warning(f"[Populator] LLM 提取失败: {company_name} {year}")
            return 0

        # Step 4: 写入 SQL
        count = self._save_metrics(company_id, year, extracted)

        # Step 5: 计算派生指标
        count += self._compute_derived(company_id, year)

        logger.info(f"[Populator] 完成: {company_name} {year}, {count} 个指标")
        return count

    def populate_all(self) -> dict:
        """
        批量填充所有已知的 (公司, 年份) 对。

        以硬编码列表为主（来自 data/documents/ 目录已知文档），
        ChromaDB 动态检测为辅（发现新文档时自动追加）。
        """
        # ── 主列表：已知文档对应的 (公司, 年份) 对 ──
        pairs = [
            ("贵州茅台", 2023), ("贵州茅台", 2024),
            ("比亚迪", 2023), ("比亚迪", 2024),
            ("腾讯控股", 2023), ("腾讯控股", 2024),
            ("五粮液", 2024),
            ("宁德时代", 2024),
        ]

        # ── 动态补充：ChromaDB 中可能有新文档，合并去重 ──
        try:
            from rag.vector_store import get_document_list
            docs = get_document_list()
            seen = set(pairs)
            for doc in docs:
                pair = self._parse_filename(doc["filename"])
                if pair[0] and pair[1] and pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)
                    logger.info(f"[Populator] 新发现: {pair}")
        except Exception as e:
            logger.debug(f"ChromaDB 动态检测跳过（使用主列表）: {e}")

        logger.info(f"[Populator] 发现 {len(pairs)} 个 (公司, 年份) 对: {pairs}")

        total_metrics = 0
        success = 0
        failed = 0

        for company, year in pairs:
            try:
                count = self.populate_company(company, year)
                if count > 0:
                    success += 1
                    total_metrics += count
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"[Populator] 失败: {company} {year}: {e}")
                failed += 1

        result = {
            "total_pairs": len(pairs),
            "success": success,
            "failed": failed,
            "total_metrics": total_metrics,
        }
        logger.info(f"[Populator] 全量填充完成: {result}")
        return result

    # ========== 内部方法 ==========

    def _parse_filename(self, filename: str) -> Tuple[Optional[str], Optional[int]]:
        """
        从文件名解析公司和年份。

        示例:
          "贵州茅台2024年年报.pdf" → ("贵州茅台", 2024)
          "比亚迪2024年年报.PDF" → ("比亚迪", 2024)
          "白酒行业2024年报综述-券商研报.docx" → (None, None)  # 行业研报，非公司文档
        """
        import re

        # 行业研报/测试数据 → 跳过
        skip_keywords = ["研报", "行业", "测试", "摘要", "综述"]
        if any(kw in filename for kw in skip_keywords):
            return None, None

        # 提取年份
        year_match = re.search(r'(\d{4})', filename)
        year = int(year_match.group(1)) if year_match else None

        # 提取公司名
        company = None
        known = {
            "贵州茅台": "贵州茅台",
            "茅台": "贵州茅台",
            "比亚迪": "比亚迪",
            "BYD": "比亚迪",
            "腾讯": "腾讯控股",
            "腾讯控股": "腾讯控股",
            "五粮液": "五粮液",
            "宁德时代": "宁德时代",
            "宁德": "宁德时代",
        }
        for kw, std_name in known.items():
            if kw in filename:
                company = std_name
                break

        return company, year

    def _ensure_company(self, name: str) -> int:
        """
        确保公司存在于 Company 表中，返回 id。

        如果不存在，自动使用种子数据创建。
        """
        db = SessionLocal()
        try:
            c = db.query(Company).filter_by(name=name).first()
            if not c:
                # 种子数据
                seed_aliases = {
                    "贵州茅台": ["茅台", "600519"],
                    "比亚迪": ["BYD", "002594"],
                    "腾讯控股": ["腾讯", "Tencent", "0700.HK"],
                    "五粮液": [],
                    "宁德时代": ["宁德"],
                }
                c = Company(
                    name=name,
                    aliases=seed_aliases.get(name, []),
                    industry="",
                )
                db.add(c)
                db.commit()
                logger.info(f"[Populator] 新增公司: {name}")
            return c.id
        finally:
            db.close()

    def _retrieve_chunks(self, company: str, year: int,
                          target_chunks: int = 15) -> List[dict]:
        """
        通过 RAG 检索该公司+年份的财务数据相关 chunks。

        检索策略：用公司名 + 年份 + 财务关键指标作为查询词
        """
        from rag.query_processor import process_query
        from rag.hybrid_search import hybrid_search

        # 构建多个检索 query，提高覆盖面
        search_queries = [
            f"{company} {year}年 营业收入 营业成本 净利润",
            f"{company} {year}年 总资产 总负债 净资产",
            f"{company} {year}年 经营活动现金流 投资活动 筹资活动",
        ]

        all_chunks = []
        seen = set()
        for q in search_queries:
            processed = process_query(q)
            results = hybrid_search(processed, top_k=8)  # BM25实体加权已足够，enable_entity_routing有bug会返回空
            for r in results:
                key = r["content"][:100]
                if key not in seen:
                    seen.add(key)
                    all_chunks.append(r)

        logger.debug(f"[Populator] 检索 {company} {year}: {len(all_chunks)} chunks")
        return all_chunks[:target_chunks]

    def _extract_metrics(self, company: str, year: int,
                          chunks: List[dict]) -> Optional[dict]:
        """
        一次 LLM 调用批量提取全部标准指标。
        """
        # 构建上下文（拼接 chunks）
        context_parts = []
        for i, s in enumerate(chunks, 1):
            context_parts.append(f"[来源{i}] {s.get('source', '')} 页码:{s.get('page', '')}\n{s['content']}")
        context = "\n\n".join(context_parts)

        prompt = BULK_EXTRACT_PROMPT.format(company=company, year=year, context=context)

        from rag.model_router import chat, TaskType
        from utils.text import parse_llm_json

        # ── Flash 提取 ──
        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                task_type=TaskType.SIMPLE,
                query=prompt,
            )
            result = parse_llm_json(response)
            filtered = {k: v for k, v in result.items() if v is not None}
            if filtered:
                logger.info(f"[Populator] Flash 原始键名 {company} {year}: {list(result.keys())}")
                logger.info(f"[Populator] Flash 提取 {company} {year}: {len(filtered)} 个指标: {list(filtered.keys())}")
                return filtered
        except Exception as e:
            logger.debug(f"[Populator] Flash 提取失败: {e}")

        # ── Pro 重试 ──
        try:
            logger.info(f"[Populator] Flash 失败，重试 Pro: {company} {year}")
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                task_type=TaskType.COMPLEX,
                query=prompt,
            )
            result = parse_llm_json(response)
            filtered = {k: v for k, v in result.items() if v is not None}
            # ── 调试：打印 LLM 原始返回的所有键名 ──
            logger.info(f"[Populator] Pro 原始键名 {company} {year}: {list(result.keys())}")
            logger.info(f"[Populator] Pro 提取 {company} {year}: {len(filtered)} 个指标: {list(filtered.keys())}")
            return filtered
        except Exception as e:
            logger.warning(f"[Populator] Pro 重试也失败: {e}")
            return None

    # ── 指标名别名（LLM 可能返回非标准名称）──
    METRIC_ALIASES = {
        "营业总收入": "营业收入", "营收": "营业收入", "收入": "营业收入",
        "营业总成本": "营业成本",
        "归母净利润": "净利润", "归属于母公司股东的净利润": "净利润",
        "利润总额": "净利润", "净利": "净利润",
        "资产总计": "总资产",
        "负债合计": "总负债", "负债": "总负债",
        "权益": "净资产", "股东权益": "净资产", "所有者权益": "净资产",
        "流动资产合计": "流动资产",
        "流动负债合计": "流动负债",
        "存货净额": "存货",
        "经营现金流": "经营活动产生的现金流量净额",
        "经营活动现金流净额": "经营活动产生的现金流量净额",
        "投资现金流": "投资活动产生的现金流量净额",
        "筹资现金流": "筹资活动产生的现金流量净额",
        "固定资产": "资本支出",
        "基本每股收益": "基本每股收益", "EPS": "基本每股收益",
        "研发投入": "研发费用",
        "期初资产总计": "期初总资产", "期初总资产": "期初总资产",
        "期初所有者权益": "期初净资产",
    }

    def _normalize_metric(self, name: str) -> str:
        """标准化指标名（别名 → 标准名）"""
        return self.METRIC_ALIASES.get(name, name)

    def _save_metrics(self, company_id: int, year: int,
                       data: dict) -> int:
        """
        将提取的指标写入 FinancialData 表（INSERT OR REPLACE）。
        自动标准化 LLM 返回的非标准指标名。
        """
        db = SessionLocal()
        count = 0
        try:
            for raw_name, value in data.items():
                if not isinstance(value, (int, float)):
                    continue
                # 标准化指标名
                metric_name = self._normalize_metric(raw_name)
                if metric_name not in STANDARD_METRICS:
                    logger.info(f"[Populator] 跳过非标准指标: '{raw_name}'→'{metric_name}' (不在STANDARD_METRICS中)")
                    continue

                # INSERT OR REPLACE
                existing = db.query(FinancialData).filter_by(
                    company_id=company_id, year=year, metric_name=metric_name,
                ).first()
                if existing:
                    existing.value = float(value)
                    existing.confidence = 0.9
                else:
                    db.add(FinancialData(
                        company_id=company_id, year=year,
                        metric_name=metric_name, value=float(value),
                        unit="亿元", confidence=0.9,
                        is_derived=0,
                    ))
                count += 1
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[Populator] 写入失败: {e}")
        finally:
            db.close()
        return count

    def _compute_derived(self, company_id: int, year: int) -> int:
        """
        计算派生指标：毛利率、净利率、资产负债率。
        从已存储的基础指标中计算，标记 is_derived=1。
        """
        db = SessionLocal()
        count = 0
        try:
            # 获取该年所有指标
            rows = db.query(FinancialData).filter_by(
                company_id=company_id, year=year,
            ).all()
            values = {r.metric_name: r.value for r in rows}

            derived = []
            # 毛利率 = (营业收入 - 营业成本) / 营业收入 × 100
            if "营业收入" in values and "营业成本" in values and values["营业收入"] != 0:
                gpm = round((values["营业收入"] - values["营业成本"]) / values["营业收入"] * 100, 2)
                derived.append(("毛利率", gpm))

            # 净利率 = 净利润 / 营业收入 × 100
            if "净利润" in values and "营业收入" in values and values["营业收入"] != 0:
                npm = round(values["净利润"] / values["营业收入"] * 100, 2)
                derived.append(("净利率", npm))

            # 资产负债率 = 总负债 / 总资产 × 100
            if "总负债" in values and "总资产" in values and values["总资产"] != 0:
                debt_ratio = round(values["总负债"] / values["总资产"] * 100, 2)
                derived.append(("资产负债率", debt_ratio))

            for metric, val in derived:
                existing = db.query(FinancialData).filter_by(
                    company_id=company_id, year=year, metric_name=metric,
                ).first()
                if existing:
                    existing.value = val
                else:
                    db.add(FinancialData(
                        company_id=company_id, year=year,
                        metric_name=metric, value=val,
                        unit="%", confidence=1.0, is_derived=1,
                    ))
                count += 1

            db.commit()
        except Exception as e:
            db.rollback()
            logger.debug(f"[Populator] 派生指标计算失败: {e}")
        finally:
            db.close()
        return count


# ==================== CLI 入口 ====================

if __name__ == "__main__":
    # 确保 backend 在 Python path 中
    sys.path.insert(0, str(Path(__file__).parent.parent))

    import argparse
    parser = argparse.ArgumentParser(description="结构化财务数据填充工具")
    parser.add_argument("--all", action="store_true", help="批量回填所有已有文档")
    parser.add_argument("--company", type=str, help="指定公司名")
    parser.add_argument("--year", type=int, help="指定年份")
    args = parser.parse_args()

    # 初始化数据库
    from db import init_db
    init_db()

    populator = DataPopulator()

    if args.all:
        result = populator.populate_all()
        print(f"\n填充完成: {result}")
    elif args.company and args.year:
        count = populator.populate_company(args.company, args.year)
        print(f"\n{args.company} {args.year}: {count} 个指标")
    else:
        parser.print_help()
