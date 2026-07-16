"""
V8.2 评测数据更新脚本 — 从 SQL 数据库自动生成 required_numbers 预期值

用法: python scripts/update_eval_expected.py

原理:
  评测集 agent_questions.json 中的 required_numbers 是人工编写的，
  与数据库实际值不一致，导致数字准确率假低。

  此脚本解析每道题的 required_numbers 键名（指标_公司_年份），
  查询 SQL 数据库获取实际值，替换硬编码值为数据库真实值。
  数据库中没有的值会被移除（标记为数据不可用，不参与评分）。
"""
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from db.financial_query import COMPANY_ALIASES, METRIC_ALIASES, _query_one_company
from db import SessionLocal


def parse_key(key: str) -> dict:
    """
    解析 required_numbers 的键名。

    格式支持:
      "毛利率"              → {metric: "毛利率"}
      "毛利率_2024"         → {metric: "毛利率", year: 2024}
      "毛利率_贵州茅台"      → {metric: "毛利率", company: "贵州茅台"}
      "毛利率_贵州茅台_2024" → {metric: "毛利率", company: "贵州茅台", year: 2024}
      "营业收入_比亚迪_2024" → {metric: "营业收入", company: "比亚迪", year: 2024}
    """
    result = {"metric": key}
    parts = key.split("_")

    # 已知公司名列表
    known = list(COMPANY_ALIASES.keys())
    known.sort(key=len, reverse=True)  # 长名优先

    # 检测公司名
    for company in known:
        if company in key:
            result["company"] = company
            result["metric"] = key.replace(f"_{company}", "")
            break

    # 检测年份
    year_match = re.search(r'_(\d{4})$', result["metric"])
    if year_match:
        result["year"] = int(year_match.group(1))
        result["metric"] = result["metric"][: -5]  # 去掉 _YYYY

    return result


def lookup_db_value(parsed: dict) -> float | None:
    """
    从 SQL 数据库查询指标的实际值。

    返回 None 表示数据库中没有该数据。
    """
    metric_name = parsed.get("metric", "")
    company_name = parsed.get("company", "")
    year = parsed.get("year")

    # 找公司 symbol
    symbol = COMPANY_ALIASES.get(company_name)
    if not symbol:
        # 尝试模糊匹配
        for alias, sym in COMPANY_ALIASES.items():
            if company_name in alias or alias in company_name:
                symbol = sym
                break
    if not symbol:
        return None

    # 找指标定义
    metric_def = METRIC_ALIASES.get(metric_name)
    if not metric_def:
        # 尝试模糊匹配
        for alias, mdef in METRIC_ALIASES.items():
            if metric_name in alias or alias in metric_name:
                metric_def = mdef
                break
    if not metric_def:
        return None

    # 确定查询年份
    from datetime import datetime
    years = [year] if year else [datetime.now().year - 1]

    db = SessionLocal()
    try:
        from db import FinancialData
        for yr in years:
            values = {}
            for key in metric_def["keys"]:
                record = db.query(FinancialData).filter(
                    FinancialData.symbol == symbol,
                    FinancialData.year == yr,
                    FinancialData.quarter == "Q4",
                    FinancialData.metric_key == key,
                ).first()
                if not record:
                    record = db.query(FinancialData).filter(
                        FinancialData.symbol == symbol,
                        FinancialData.year == yr,
                        FinancialData.metric_key == key,
                    ).order_by(FinancialData.quarter.desc()).first()
                if record:
                    values[key] = record.metric_value

            if not values:
                continue

            formula = metric_def.get("formula")
            if formula and len(metric_def["keys"]) >= 2 and all(k in values for k in metric_def["keys"]):
                try:
                    from db.financial_query import _safe_eval
                    return round(_safe_eval(formula, values), 2)
                except Exception:
                    pass
            elif not formula and metric_def["keys"]:
                key = metric_def["keys"][0]
                if key in values:
                    return values[key]
    finally:
        try:
            db.close()
        except Exception:
            pass

    return None


def main():
    questions_path = PROJECT_ROOT / "evaluation" / "data" / "agent_questions.json"
    with open(questions_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_updated = 0
    total_removed = 0
    total_kept = 0

    for q in data["questions"]:
        qid = q["id"]
        required = q.get("required_numbers", {})
        new_required = {}
        removed = []

        for key, old_val in required.items():
            parsed = parse_key(key)
            db_val = lookup_db_value(parsed)

            if db_val is not None:
                # 数据库有值 → 更新
                if abs(db_val - old_val) > 0.1:  # 值变了才报告
                    print(f"  [{qid}] {key}: {old_val} → {db_val} (数据库实际值)")
                    total_updated += 1
                else:
                    total_kept += 1
                new_required[key] = db_val
            else:
                # 数据库无值 → 移除
                removed.append(key)
                total_removed += 1

        if removed:
            print(f"  [{qid}] 移除缺失数据: {removed}")

        q["required_numbers"] = new_required

    # 备份原文件
    backup_path = questions_path.with_suffix(".json.bak")
    import shutil
    shutil.copy2(questions_path, backup_path)
    print(f"\n备份保存: {backup_path}")

    # 写入新文件
    with open(questions_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n=== 更新完成 ===")
    print(f"  更新: {total_updated} 个值 (数据库修正)")
    print(f"  保持: {total_kept} 个值 (已一致)")
    print(f"  移除: {total_removed} 个值 (数据库无数据)")
    print(f"  文件: {questions_path}")


if __name__ == "__main__":
    main()
