"""
金融公司数据补填脚本 — P0-1

问题: 4家金融公司（招商银行/中国平安/平安银行/中信证券）缺 net_profit_attr_parent，
     2家（招商银行/平安银行）额外缺少所有 equity 字段（equity_attr_parent 和 total_equity），
     导致 ROE/净利率/ROA 等公式计算失败。

根因: 数据采集时未采集 net_profit_attr_parent（归母净利润），金融企业 equity 数据覆盖不全。

修复（三步）:
  1. net_profit_attr_parent ← net_profit（金融企业少数股东占比<1%，两值接近）
  2. total_equity ← total_assets - total_liabilities（会计恒等式，招商银行/平安银行专用）
  3. equity_attr_parent ← total_equity（借助步骤2补上的 total_equity）

用法:
  python scripts/backfill_financial_data.py [--dry-run] [--rollback]

  --dry-run   预览将要插入的数据，不实际写入
  --rollback  回滚本次补填（删除 source 含 ':backfill' 标记的行）
"""

import sys
import os
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from db.database import SessionLocal
from db.financial_models import FinancialData, Company
from loguru import logger


def _insert_or_skip(db, company_id: int, symbol: str, year: int, quarter: str,
                    metric_key: str, metric_value: float, report_date: str, source: str) -> int:
    """插入一行，如果目标数据已存在则跳过。返回 1=插入, 0=跳过。"""
    existing = db.query(FinancialData).filter(
        FinancialData.company_id == company_id,
        FinancialData.year == year,
        FinancialData.quarter == quarter,
        FinancialData.metric_key == metric_key,
    ).first()
    if existing:
        return 0
    db.add(FinancialData(
        company_id=company_id,
        symbol=symbol,
        year=year,
        quarter=quarter,
        metric_key=metric_key,
        metric_value=metric_value,
        report_date=report_date,
        source=f"{source}:backfill",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))
    return 1


def backfill_net_profit_attr_parent(db, dry_run: bool = False) -> int:
    """步骤1: net_profit_attr_parent ← net_profit"""
    # 找有 net_profit 但缺 net_profit_attr_parent 的公司
    has_source = set(
        r[0] for r in db.query(FinancialData.company_id).filter(
            FinancialData.metric_key == "net_profit"
        ).distinct()
    )
    has_target = set(
        r[0] for r in db.query(FinancialData.company_id).filter(
            FinancialData.metric_key == "net_profit_attr_parent"
        ).distinct()
    )
    missing_ids = has_source - has_target

    if not missing_ids:
        logger.info("  [net_profit_attr_parent] 无需补填")
        return 0

    records = []
    for cid in missing_ids:
        company = db.query(Company).filter(Company.id == cid).first()
        rows = db.query(FinancialData).filter(
            FinancialData.company_id == cid,
            FinancialData.metric_key == "net_profit",
        ).order_by(FinancialData.year, FinancialData.quarter).all()
        for row in rows:
            records.append((company.id, company.symbol, row.year, row.quarter,
                          row.metric_value, row.report_date))

    logger.info(f"  [net_profit_attr_parent] 将补填 {len(records)} 条记录 ← net_profit")

    if dry_run:
        for cid, sym, year, q, val, _ in records[:5]:
            logger.info(f"    [DRY-RUN] ... {sym} {year} {q}: {val}")
        return len(records)

    inserted = 0
    for cid, sym, year, q, val, rdate in records:
        inserted += _insert_or_skip(db, cid, sym, year, q, "net_profit_attr_parent",
                                    val, rdate, "net_profit")
    return inserted


def backfill_computed_equity(db, dry_run: bool = False) -> int:
    """步骤2: 对同时缺 total_equity 和 equity_attr_parent 的公司，用会计恒等式计算"""
    has_te = set(r[0] for r in db.query(FinancialData.company_id).filter(
        FinancialData.metric_key == "total_equity").distinct())
    has_ea = set(r[0] for r in db.query(FinancialData.company_id).filter(
        FinancialData.metric_key == "equity_attr_parent").distinct())
    # 两个都没有的公司
    missing_both = set(
        r[0] for r in db.query(FinancialData.company_id).distinct()
    ) - has_te - has_ea

    if not missing_both:
        logger.info("  [computed total_equity] 无需补填")
        return 0

    inserted = 0
    for cid in missing_both:
        company = db.query(Company).filter(Company.id == cid).first()
        # 获取所有季度的 total_assets 和 total_liabilities
        assets = {
            (r.year, r.quarter): r.metric_value
            for r in db.query(FinancialData).filter(
                FinancialData.company_id == cid,
                FinancialData.metric_key == "total_assets",
            ).all()
        }
        liabilities = {
            (r.year, r.quarter): r.metric_value
            for r in db.query(FinancialData).filter(
                FinancialData.company_id == cid,
                FinancialData.metric_key == "total_liabilities",
            ).all()
        }
        # 取交集（两个都要有才能算）
        common_quarters = set(assets.keys()) & set(liabilities.keys())
        records = sorted(common_quarters)

        logger.info(f"  [computed total_equity] {company.name}: {len(records)} 条 ← assets - liabilities")

        for year, quarter in records:
            eq_value = assets[(year, quarter)] - liabilities[(year, quarter)]
            # 取同期任意一条的 report_date（优先取 assets 的）
            rdate = db.query(FinancialData.report_date).filter(
                FinancialData.company_id == cid,
                FinancialData.year == year,
                FinancialData.quarter == quarter,
                FinancialData.metric_key == "total_assets",
            ).scalar()
            if dry_run:
                logger.info(f"    [DRY-RUN] {company.name} {year} {quarter}: "
                          f"total_equity = {assets[(year,quarter)]} - {liabilities[(year,quarter)]} = {eq_value}")
            else:
                inserted += _insert_or_skip(db, cid, company.symbol, year, quarter,
                                           "total_equity", eq_value, rdate, "computed")

    return inserted


def backfill_equity_attr_parent(db, dry_run: bool = False) -> int:
    """步骤3: equity_attr_parent ← total_equity（此时 total_equity 已包含步骤2的计算值）"""
    has_source = set(r[0] for r in db.query(FinancialData.company_id).filter(
        FinancialData.metric_key == "total_equity").distinct())
    has_target = set(r[0] for r in db.query(FinancialData.company_id).filter(
        FinancialData.metric_key == "equity_attr_parent").distinct())
    missing_ids = has_source - has_target

    if not missing_ids:
        logger.info("  [equity_attr_parent] 无需补填")
        return 0

    records = []
    for cid in missing_ids:
        company = db.query(Company).filter(Company.id == cid).first()
        rows = db.query(FinancialData).filter(
            FinancialData.company_id == cid,
            FinancialData.metric_key == "total_equity",
        ).order_by(FinancialData.year, FinancialData.quarter).all()
        for row in rows:
            records.append((company.id, company.symbol, row.year, row.quarter,
                          row.metric_value, row.report_date))

    logger.info(f"  [equity_attr_parent] 将补填 {len(records)} 条记录 ← total_equity")

    if dry_run:
        for cid, sym, year, q, val, _ in records[:5]:
            logger.info(f"    [DRY-RUN] ... {sym} {year} {q}: {val}")
        return len(records)

    inserted = 0
    for cid, sym, year, q, val, rdate in records:
        inserted += _insert_or_skip(db, cid, sym, year, q, "equity_attr_parent",
                                    val, rdate, "total_equity")
    return inserted


def rollback_backfill(db):
    """删除 source 包含 ':backfill' 标记的行"""
    rows = db.query(FinancialData).filter(FinancialData.source.like('%:backfill%')).all()
    count = len(rows)
    if count == 0:
        logger.info("  没有需要回滚的补填数据。")
        return 0
    for row in rows:
        db.delete(row)
    return count


def main():
    parser = argparse.ArgumentParser(description="金融公司财务数据补填")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际写入")
    parser.add_argument("--rollback", action="store_true", help="回滚补填数据")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.rollback:
            logger.info("回滚补填数据...")
            count = rollback_backfill(db)
            db.commit()
            logger.info(f"已回滚 {count} 条记录")
            return

        total = 0
        total += backfill_net_profit_attr_parent(db, dry_run=args.dry_run)
        total += backfill_computed_equity(db, dry_run=args.dry_run)
        total += backfill_equity_attr_parent(db, dry_run=args.dry_run)

        if args.dry_run:
            logger.info(f"\n预览完成: 共 {total} 条待补填记录（未写入）")
            logger.info("   执行 python scripts/backfill_financial_data.py 进行实际写入")
        else:
            db.commit()
            logger.info(f"\n补填完成: 共写入 {total} 条记录")

    except Exception as e:
        db.rollback()
        logger.error(f"补填失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
