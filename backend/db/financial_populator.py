"""
财务数据填充器 — 从 AKShare 获取真实财务数据并写入 SQL

用法:
    python -m db.financial_populator --all              # 填充预设全部公司
    python -m db.financial_populator --symbol 600519    # 单个公司
    python -m db.financial_populator --top 50           # A股前50大市值

数据源:
    AKShare (新浪财经) — 利润表/资产负债表/现金流量表
    频率: 年度 + 季度

设计原则:
    - AKShare 返回的中文指标名 → 映射到我们定义的 metric_key
    - 缺失指标跳过（不报错），已有指标 upsert
    - 零 LLM 参与，纯规则映射
"""
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from loguru import logger

# ── 指标映射：AKShare 中文名 → metric_key ──
# AKShare 的列名极其冗长（如"归属于母公司所有者的净利润"），
# 这里只映射我们关心的核心指标，其余跳过。

METRIC_NAME_MAP: Dict[str, str] = {
    # ── 利润表 ──
    "营业收入": "revenue",
    "营业总收入": "revenue",
    "营业成本": "cost_of_revenue",
    "营业总成本": "cost_of_revenue",
    "销售费用": "selling_expenses",
    "管理费用": "admin_expenses",
    "研发费用": "rd_expenses",
    "财务费用": "finance_expenses",
    "利息费用": "interest_expense",
    "利息收入": "interest_income",
    "投资收益": "investment_income",
    "营业利润": "operating_profit",
    "利润总额": "total_profit",
    "所得税费用": "income_tax",
    "净利润": "net_profit",
    "归属于母公司所有者的净利润": "net_profit_attr_parent",
    "归属于母公司股东的净利润": "net_profit_attr_parent",
    "少数股东损益": "minority_interest",
    "基本每股收益": "eps",
    "稀释每股收益": "diluted_eps",
    "其他综合收益": "other_comprehensive_income",
    "综合收益总额": "total_comprehensive_income",
    "营业税金及附加": "business_tax_surcharge",
    # ── 资产负债表 ──
    "资产总计": "total_assets",
    "流动资产合计": "current_assets",
    "货币资金": "cash_and_equivalents",
    "交易性金融资产": "trading_financial_assets",
    "应收票据及应收账款": "receivables",
    "存货": "inventory",
    "非流动资产合计": "non_current_assets",
    "固定资产": "fixed_assets",
    "在建工程": "construction_in_progress",
    "无形资产": "intangible_assets",
    "商誉": "goodwill",
    "长期股权投资": "long_term_investments",
    "负债合计": "total_liabilities",
    "流动负债合计": "current_liabilities",
    "短期借款": "short_term_borrowings",
    "应付票据及应付账款": "payables",
    "合同负债": "contract_liabilities",
    "非流动负债合计": "non_current_liabilities",
    "长期借款": "long_term_borrowings",
    "应付债券": "bonds_payable",
    "所有者权益合计": "total_equity",
    "归属于母公司股东权益合计": "equity_attr_parent",
    "实收资本（或股本）": "share_capital",
    "资本公积": "capital_reserve",
    "盈余公积": "surplus_reserve",
    "未分配利润": "retained_earnings",
    # ── 现金流量表 ──
    "经营活动现金流入小计": "operating_cf_in",
    "经营活动现金流出小计": "operating_cf_out",
    "经营活动产生的现金流量净额": "operating_cf",
    "投资活动现金流入小计": "investing_cf_in",
    "投资活动现金流出小计": "investing_cf_out",
    "投资活动产生的现金流量净额": "investing_cf",
    "筹资活动现金流入小计": "financing_cf_in",
    "筹资活动现金流出小计": "financing_cf_out",
    "筹资活动产生的现金流量净额": "financing_cf",
    "现金及现金等价物净增加额": "net_change_in_cash",
    "期初现金及现金等价物余额": "cash_beginning",
    "期末现金及现金等价物余额": "cash_ending",
}

# ── 预设公司列表（A股核心标的）──
DEFAULT_COMPANIES = [
    ("600519", "贵州茅台", "SH", "白酒"),
    ("000858", "五粮液", "SZ", "白酒"),
    ("002594", "比亚迪", "SZ", "新能源汽车"),
    ("300750", "宁德时代", "SZ", "新能源电池"),
    ("000333", "美的集团", "SZ", "家电"),
    ("600036", "招商银行", "SH", "银行"),
    ("601318", "中国平安", "SH", "保险"),
    ("600276", "恒瑞医药", "SH", "医药"),
    ("002415", "海康威视", "SZ", "安防"),
    ("600900", "长江电力", "SH", "电力"),
    ("000001", "平安银行", "SZ", "银行"),
    ("600030", "中信证券", "SH", "券商"),
    ("002230", "科大讯飞", "SZ", "AI"),
    ("601012", "隆基绿能", "SH", "光伏"),
    ("600809", "山西汾酒", "SH", "白酒"),
    ("000568", "泸州老窖", "SZ", "白酒"),
    ("600887", "伊利股份", "SH", "食品"),
    ("002304", "洋河股份", "SZ", "白酒"),
    ("000725", "京东方A", "SZ", "面板"),
    ("688981", "中芯国际", "SH", "半导体"),
]

# 额外代码→名称映射（手工注册港股和未覆盖公司）
EXTRA_SYMBOLS: Dict[str, Tuple[str, str, str]] = {
    "00700": ("腾讯控股", "HK", "互联网"),
}


def _clean_metric_name(raw: str) -> str:
    """清理 AKShare 返回的指标名，去掉多余前缀/后缀"""
    # 去掉常见前缀
    for prefix in ["其中：", "其中:", "减：", "减:", "加：", "加:"]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    return raw.strip()


def query_financial_data(symbol: str, years: int = 5) -> List[Dict]:
    """
    从 AKShare 获取一家公司的财务数据（利润表+资产负债表+现金流）。

    参数:
        symbol: 股票代码（600519/002594等）
        years: 拉取最近 N 年数据

    返回:
        [{"symbol": "600519", "year": 2024, "quarter": "Q4",
          "metric_key": "revenue", "metric_value": 1708.99e8,
          "report_date": "2024-12-31"}, ...]
    """
    import akshare as ak

    prefix = "sh" if symbol.startswith(("6", "9")) else "sz"
    full_symbol = f"{prefix}{symbol}"

    results = []
    report_types = ["利润表", "资产负债表", "现金流量表"]

    for report_type in report_types:
        try:
            df = ak.stock_financial_report_sina(stock=full_symbol, symbol=report_type)
        except Exception as e:
            logger.warning(f"[AKShare] {report_type} 获取失败 ({symbol}): {e}")
            continue

        if df is None or df.empty:
            logger.warning(f"[AKShare] {report_type} 空数据 ({symbol})")
            continue

        # 第一列是报告日期，其余是指标
        date_col = df.columns[0]
        metric_cols = df.columns[1:]

        for _, row in df.iterrows():
            report_date_str = str(row[date_col])
            year, quarter = _parse_report_date(report_date_str)

            # 只取最近 N 年的年度报告 + 最近4个季度
            current_year = datetime.now().year
            if year < current_year - years:
                continue

            for col in metric_cols:
                raw_name = _clean_metric_name(str(col))
                metric_key = METRIC_NAME_MAP.get(raw_name)
                if metric_key is None:
                    continue  # 不在关注的指标列表中

                try:
                    value = float(row[col])
                except (ValueError, TypeError):
                    continue

                # 注意：0.0 是合法值（如零债务公司短期借款=0），不能过滤

                results.append({
                    "symbol": symbol,
                    "year": year,
                    "quarter": quarter,
                    "metric_key": metric_key,
                    "metric_value": value,
                    "report_date": report_date_str,
                    "source": "AKShare",
                })

    logger.info(f"[AKShare] {symbol}: {len(results)} 条财务指标")
    return results


def _parse_report_date(date_str: str) -> Tuple[int, str]:
    """
    解析报告日期 → (年份, 季度)

    "20241231" → (2024, "Q4")
    "20240930" → (2024, "Q3")
    "20240630" → (2024, "Q2")
    "20240331" → (2024, "Q1")
    """
    date_str = date_str.strip()
    # 支持 "20241231" 和 "2024-12-31" 两种格式
    match = re.match(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", date_str)
    if not match:
        logger.warning(f"无法解析日期格式: {date_str}，回退为当前年份")
        return datetime.now().year, "annual"
    year, month, _ = int(match.group(1)), int(match.group(2)), int(match.group(3))
    quarter_map = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
    return year, quarter_map.get(month, "annual")


def populate_company(symbol: str, name: str = "", market: str = "SH",
                     sector: str = "", years: int = 5) -> int:
    """
    填充单家公司：注册公司 + 拉取AKShare数据 + 写入SQL。

    返回写入的指标数。
    """
    from db import SessionLocal
    from db.financial_models import Company, FinancialData

    db = SessionLocal()
    count = 0

    try:
        # 1. 注册公司
        company = db.query(Company).filter(Company.symbol == symbol).first()
        if not company:
            company = Company(symbol=symbol, name=name, market=market, sector=sector)
            db.add(company)
            db.commit()
            logger.info(f"  注册公司: {name} ({symbol})")
        elif name and not company.name:
            company.name = name

        # 2. 从 AKShare 获取数据并批内去重
        raw_data = query_financial_data(symbol, years=years)
        # 批内去重：同(symbol, year, quarter, metric_key)只保留最后一个值
        seen = {}
        for item in raw_data:
            key = (item["symbol"], item["year"], item["quarter"], item["metric_key"])
            seen[key] = item  # 后来的覆盖前面的
        data = list(seen.values())
        logger.debug(f"  去重: {len(raw_data)} → {len(data)} 条")

        # 3. 批量 upsert：DB 已有则更新，否则插入
        for item in data:
            existing = db.query(FinancialData).filter(
                FinancialData.symbol == item["symbol"],
                FinancialData.year == item["year"],
                FinancialData.quarter == item["quarter"],
                FinancialData.metric_key == item["metric_key"],
            ).first()

            if existing:
                existing.metric_value = item["metric_value"]
                existing.updated_at = datetime.now()
            else:
                db.add(FinancialData(
                    company_id=company.id,
                    symbol=item["symbol"],
                    year=item["year"],
                    quarter=item["quarter"],
                    metric_key=item["metric_key"],
                    metric_value=item["metric_value"],
                    report_date=item["report_date"],
                    source=item["source"],
                ))
            count += 1

        db.commit()
        logger.info(f"  {symbol} {name}: {count} 条指标写入成功")

    except Exception as e:
        db.rollback()
        logger.error(f"  {symbol} 填充失败: {e}")
    finally:
        db.close()

    return count


def populate_all(years: int = 5) -> Dict[str, int]:
    """批量填充预设公司列表"""
    results = {}
    for symbol, name, market, sector in DEFAULT_COMPANIES:
        try:
            count = populate_company(symbol, name, market, sector, years)
            results[symbol] = count
        except Exception as e:
            logger.error(f"[{symbol}] {name} 失败: {e}")
            results[symbol] = 0
    total = sum(results.values())
    logger.info(f"批量填充完成: {len(results)} 家公司, {total} 条指标")
    return results


# ==================== CLI ====================

if __name__ == "__main__":
    # 初始化数据库
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from db import init_db
    # 必须先导入模型再 init_db
    import db.financial_models  # noqa
    init_db()

    if "--all" in sys.argv:
        populate_all()
    elif "--symbol" in sys.argv:
        try:
            idx = sys.argv.index("--symbol")
            if idx + 1 >= len(sys.argv):
                print("错误: --symbol 需要指定股票代码")
                sys.exit(1)
            symbol = sys.argv[idx + 1]
            extra = EXTRA_SYMBOLS.get(symbol, ("", "SH", ""))
            populate_company(symbol, extra[0], extra[1], extra[2])
        except ValueError:
            print("错误: --symbol 缺少参数值")
            sys.exit(1)
    elif "--top" in sys.argv:
        try:
            idx = sys.argv.index("--top")
            n = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 10
            for sym, name, mkt, sector in DEFAULT_COMPANIES[:n]:
                populate_company(sym, name, mkt, sector)
        except (ValueError, IndexError):
            print("错误: --top 需要指定数量（如 --top 10）")
            sys.exit(1)
    else:
        print("用法:")
        print("  python -m db.financial_populator --all           # 填充全部预设公司")
        print("  python -m db.financial_populator --symbol 600519  # 单个公司")
        print("  python -m db.financial_populator --top 10          # A股前10大")
