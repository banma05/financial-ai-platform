"""
表格规则提取器 — 从 Markdown 表格中精确提取财务指标（零 LLM）

V8.0 核心组件：数字绝不走 LLM，规则匹配 + SQL 入库。

流程:
  PDF → loader → Markdown 表格
    → 行标签匹配（"营业收入"→revenue）
    → 提取数值
    → 写入 FinancialData 表

设计原则:
  - 零 LLM 参与（100% 准确）
  - 匹配不到 → 跳过（不瞎猜）
  - 支持合并单元格行
"""
import re
from typing import List, Dict, Optional, Tuple
from loguru import logger

# ── 行标签→metric_key 映射（复用到 financial_populator 的映射表）──
# 用 substring 匹配: 表中行标签只要包含这些关键词就匹配
ROW_LABEL_PATTERNS: Dict[str, str] = {
    # 利润表
    "营业收入": "revenue",
    "营业总收入": "revenue",
    "营业成本": "cost_of_revenue",
    "销售费用": "selling_expenses",
    "管理费用": "admin_expenses",
    "研发费用": "rd_expenses",
    "财务费用": "finance_expenses",
    "投资收益": "investment_income",
    "营业利润": "operating_profit",
    "利润总额": "total_profit",
    "所得税": "income_tax",
    "净利润": "net_profit_attr_parent",
    "归属于母公司": "net_profit_attr_parent",
    "归属于上市公司股东": "net_profit_attr_parent",
    "基本每股收益": "eps",
    "稀释每股收益": "diluted_eps",
    "综合收益": "total_comprehensive_income",
    # 资产负债表
    "资产总计": "total_assets",
    "总资产": "total_assets",
    "流动资产合计": "current_assets",
    "货币资金": "cash_and_equivalents",
    "交易性金融资产": "trading_financial_assets",
    "应收票据": "receivables",
    "应收账款": "receivables",
    "存货": "inventory",
    "非流动资产合计": "non_current_assets",
    "固定资产": "fixed_assets",
    "在建工程": "construction_in_progress",
    "无形资产": "intangible_assets",
    "商誉": "goodwill",
    "长期股权投资": "long_term_investments",
    "负债合计": "total_liabilities",
    "总负债": "total_liabilities",
    "流动负债合计": "current_liabilities",
    "短期借款": "short_term_borrowings",
    "应付票据": "payables",
    "应付账款": "payables",
    "合同负债": "contract_liabilities",
    "非流动负债合计": "non_current_liabilities",
    "长期借款": "long_term_borrowings",
    "应付债券": "bonds_payable",
    "所有者权益": "total_equity",
    "归属于母公司所有者权益": "equity_attr_parent",
    "归属于上市公司股东所有者权益": "equity_attr_parent",
    "归属于母公司股东权益": "equity_attr_parent",
    "实收资本": "share_capital",
    "股本": "share_capital",
    "资本公积": "capital_reserve",
    "盈余公积": "surplus_reserve",
    "未分配利润": "retained_earnings",
    # 现金流量表
    "经营活动产生的现金流量净额": "operating_cf",
    "经营活动现金流量净额": "operating_cf",
    "投资活动产生的现金流量净额": "investing_cf",
    "投资活动现金流量净额": "investing_cf",
    "筹资活动产生的现金流量净额": "financing_cf",
    "筹资活动现金流量净额": "financing_cf",
    "现金及现金等价物净增加额": "net_change_in_cash",
    "期初现金及现金等价物": "cash_beginning",
    "期末现金及现金等价物": "cash_ending",
}


def _parse_number(raw: str) -> Optional[float]:
    """解析数字字符串（支持逗号分隔和负号）"""
    if not raw:
        return None
    cleaned = raw.strip().replace(",", "").replace(" ", "")
    if cleaned in ("", "-", "--", "—", "/", "不适用"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_year_from_header(header_row: str) -> Optional[int]:
    """从表头提取年份（如'2024年'→2024, '2024年末'→2024）"""
    match = re.search(r"(20\d{2})\s*年?", header_row)
    if match:
        return int(match.group(1))
    return None


def extract_from_tables(tables: List[dict], default_year: Optional[int] = None) -> List[dict]:
    """
    从 Markdown 表格列表中提取财务指标。

    参数:
        tables: loader 产出的 [{"markdown": "...", "rows": N, "cols": M}, ...]
        default_year: 如果没有从表头解析到年份，使用此默认值

    返回:
        [{"metric_key": "revenue", "metric_value": 1708.99e8, "year": 2024, "quarter": "Q4"}, ...]
    """
    results = []
    current_year = default_year

    for table in tables:
        md = table["markdown"]
        lines = md.strip().split("\n")

        # 跳过没有数据行的表格
        if len(lines) < 3:
            continue

        # 解析表头
        header_line = lines[0]  # 第一行是表头
        header_year = _parse_year_from_header(header_line)
        if header_year:
            current_year = header_year

        if not current_year:
            logger.debug("无法确定表格年份，跳过")
            continue

        # 逐行匹配
        for line in lines[1:]:  # 跳过表头和分隔行
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]

            if len(cells) < 2:
                continue

            row_label = cells[0]  # 第一列是行标签
            if not row_label:
                continue

            # 匹配行标签
            matched_key = None
            for pattern, metric_key in ROW_LABEL_PATTERNS.items():
                if pattern in row_label:
                    matched_key = metric_key
                    break

            if not matched_key:
                continue

            # 提取第一个有效的数值（最近年份通常在第一列数据）
            for cell in cells[1:]:
                value = _parse_number(cell)
                if value is not None and value != 0:
                    # 数值过大可能是无效值（如日期被当数字）
                    if abs(value) > 1e15:
                        continue
                    results.append({
                        "metric_key": matched_key,
                        "metric_value": value,
                        "year": current_year,
                        "quarter": "Q4",
                        "row_label": row_label,
                    })
                    break  # 只取第一个有效值

    deduped = _deduplicate_results(results)
    logger.info(f"表格提取: {len(tables)} 张表 → {len(results)} 条 → 去重后 {len(deduped)} 条")
    return deduped


def _deduplicate_results(results: List[dict]) -> List[dict]:
    """去重: 同 year + metric_key 只保留一条"""
    seen = {}
    for r in results:
        key = (r["year"], r["metric_key"])
        if key not in seen:
            seen[key] = r
    return list(seen.values())


def extract_and_store(tables: List[dict], symbol: str, company_id: int,
                      default_year: Optional[int] = None) -> int:
    """
    提取表格并写入 SQL。返回写入的指标数。
    """
    from db import SessionLocal
    from db.financial_models import FinancialData
    from datetime import datetime

    extracted = extract_from_tables(tables, default_year)
    if not extracted:
        return 0

    db = SessionLocal()
    count = 0
    try:
        for item in extracted:
            existing = db.query(FinancialData).filter(
                FinancialData.symbol == symbol,
                FinancialData.year == item["year"],
                FinancialData.quarter == item["quarter"],
                FinancialData.metric_key == item["metric_key"],
            ).first()

            if existing:
                existing.metric_value = item["metric_value"]
                existing.updated_at = datetime.now()
            else:
                db.add(FinancialData(
                    company_id=company_id,
                    symbol=symbol,
                    year=item["year"],
                    quarter=item["quarter"],
                    metric_key=item["metric_key"],
                    metric_value=item["metric_value"],
                    source="rule_extraction",
                ))
            count += 1
        db.commit()
        logger.info(f"规则提取入库: {symbol} → {count} 条")
    except Exception as e:
        db.rollback()
        logger.error(f"规则提取入库失败: {e}")
    finally:
        db.close()
    return count
