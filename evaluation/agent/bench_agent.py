"""
Agent 评测脚本 — 20 题全量评测（子任务拆解准确率 + 指标覆盖率 + 耗时基准）
"""
import os
import sys
import time
import json
from pathlib import Path

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# 🔧 修复 Windows GBK 编码下 emoji 打印崩溃
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from loguru import logger
from agent.planner import Planner, BUILTIN_TEMPLATES
from agent.schemas import AnalysisPlan, AnalysisTask
from agent.graph import run_agent_sync

TEST_SET = Path(__file__).parent.parent / "data" / "agent_questions.json"

with open(TEST_SET, "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data["questions"]
meta = data["meta"]
logger.info(f"开始 Agent 评测: {len(questions)} 题, {len(meta['categories'])} 类")

planner = Planner()  # 复用同一个 Planner 实例

# ============ 评测函数 ============

def score_task_decomposition(plan: AnalysisPlan, golden: dict) -> dict:
    """对比 Planner 输出与 golden_plan"""
    tasks = plan.tasks
    if plan.requires_clarification:
        return {"score": 0.0, "status": "needs_clarification", "detail": plan.requires_clarification}

    gt = golden["golden_plan"]
    scores = {}

    # 1. 任务数量匹配度
    n = len(tasks)
    if n < gt["min_tasks"]:
        scores["count"] = n / gt["min_tasks"]
    elif n > gt["max_tasks"]:
        scores["count"] = max(0, 1 - (n - gt["max_tasks"]) / gt["max_tasks"])
    else:
        scores["count"] = 1.0

    # 2. 任务类型覆盖率
    actual_types = set(t.task_type for t in tasks)
    expected_types = set(gt["task_types"])
    scores["type_coverage"] = len(actual_types & expected_types) / len(expected_types) if expected_types else 1.0

    # 3. 必需公式覆盖率
    actual_formulas = set()
    for t in tasks:
        formula = t.params.get("formula", "")
        if formula:
            actual_formulas.add(formula)
    required = set(gt.get("required_formulas", []))
    scores["formula_coverage"] = len(actual_formulas & required) / len(required) if required else 1.0

    # 4. 图表类型覆盖率
    actual_charts = set()
    for t in tasks:
        chart_type = t.params.get("chart_type", "")
        if chart_type:
            actual_charts.add(chart_type)
    required_charts = set(gt.get("required_chart_types", []))
    scores["chart_coverage"] = len(actual_charts & required_charts) / len(required_charts) if required_charts else 1.0

    # 综合得分（加权平均）
    weights = {"count": 0.2, "type_coverage": 0.35, "formula_coverage": 0.35, "chart_coverage": 0.1}
    overall = sum(scores[k] * weights[k] for k in weights)
    scores["overall"] = round(overall, 4)

    return {"score": round(overall, 4), "status": "ok", "detail": scores, "task_count": n}


def score_indicator_coverage(report: str, expected_indicators: list) -> dict:
    """检查报告中是否包含期望的财务指标"""
    report_lower = report.lower()
    found = []
    missing = []
    for ind in expected_indicators:
        if ind.lower() in report_lower:
            found.append(ind)
        else:
            missing.append(ind)
    coverage = len(found) / len(expected_indicators) if expected_indicators else 1.0
    return {
        "coverage": round(coverage, 4),
        "found": found,
        "missing": missing,
        "total": len(expected_indicators),
    }


def score_report_structure(report: str) -> dict:
    """检查报告结构完整性（自动化结构检查，人工可读性评分见评测集说明）"""
    checks = {
        "has_summary": "一、分析摘要" in report or "分析摘要" in report,
        "has_data": "二、数据概览" in report or "数据概览" in report,
        "has_indicators": "三、指标计算" in report or "指标分析" in report or "指标计算" in report,
        "has_conclusion": "五、结论与建议" in report or "结论与建议" in report or "核心发现" in report,
        "has_chart_section": "四、可视化" in report or "图表" in report,
    }
    passed = sum(1 for v in checks.values() if v)
    return {"structure_score": passed / len(checks), "details": checks}


# ============ 主评测流程 ============

results = []
total_task_score = 0.0
total_indicator_coverage = 0.0
total_structure_score = 0.0
total_time = 0.0
by_category = {}
by_difficulty = {}
failed = []

start_all = time.time()

for i, q in enumerate(questions, 1):
    qid = q["id"]
    cat = q["category"]
    diff = q["difficulty"]
    query = q["query"]
    golden = q

    logger.info(f"\n{'='*50}")
    logger.info(f"[{i}/{len(questions)}] {qid} [{cat}][{diff}] {query[:60]}...")

    # Phase 1: Planner 评测
    plan_start = time.time()
    try:
        plan = planner.plan(query)
    except Exception as e:
        logger.error(f"  Planner 失败: {e}")
        failed.append(qid)
        continue
    plan_time = time.time() - plan_start

    task_result = score_task_decomposition(plan, golden)
    total_task_score += task_result["score"]
    logger.info(f"  Planner: score={task_result['score']:.1%} tasks={task_result.get('task_count','?')} time={plan_time:.1f}s")
    if task_result["status"] == "needs_clarification":
        logger.warning(f"  [!] 需要追问: {task_result['detail'][:80]}")

    # Phase 2: 全链路执行（同步模式，复用 Phase 1 的 Plan 避免重复 LLM 调用）
    exec_start = time.time()
    try:
        agent_result = run_agent_sync(query, plan=plan)
    except Exception as e:
        logger.error(f"  Agent 执行失败: {e}")
        failed.append(qid)
        continue
    exec_time = time.time() - exec_start
    total_time += exec_time

    # Phase 3: 报告评测
    report = agent_result.get("report", "")
    ind_result = score_indicator_coverage(report, q.get("expected_indicators", []))
    struct_result = score_report_structure(report)
    total_indicator_coverage += ind_result["coverage"]
    total_structure_score += struct_result["structure_score"]

    logger.info(f"  执行: {exec_time:.1f}s | 指标覆盖率={ind_result['coverage']:.1%} | 结构={struct_result['structure_score']:.1%}")
    if ind_result["missing"]:
        logger.info(f"  缺失指标: {ind_result['missing'][:5]}")

    # 按类别/难度分组
    for group, key in [(by_category, cat), (by_difficulty, diff)]:
        if key not in group:
            group[key] = {"count": 0, "task_score": 0.0, "ind_coverage": 0.0, "time": 0.0}
        group[key]["count"] += 1
        group[key]["task_score"] += task_result["score"]
        group[key]["ind_coverage"] += ind_result["coverage"]
        group[key]["time"] += exec_time

    results.append({
        "id": qid,
        "query": query[:80],
        "category": cat,
        "difficulty": diff,
        "task_score": task_result["score"],
        "indicator_coverage": ind_result["coverage"],
        "structure_score": struct_result["structure_score"],
        "plan_time": round(plan_time, 2),
        "exec_time": round(exec_time, 2),
        "task_count": task_result.get("task_count", 0),
        "missing_indicators": ind_result["missing"],
        "needs_clarification": task_result["status"] == "needs_clarification",
    })

elapsed = time.time() - start_all
n = len(questions)

# ============ 报告 ============
print("\n" + "=" * 70)
print(">>> Agent 20 题全量评测报告 <<<")
print("=" * 70)
print(f"题目数: {n} | 总耗时: {elapsed:.1f}s | 失败: {len(failed)} 题")
print()

print(f"| 指标 | 值 | 目标 | 达标? |")
print(f"|------|:--:|:--:|:--:|")
avg_task = total_task_score / n * 100
avg_ind = total_indicator_coverage / n * 100
avg_struct = total_structure_score / n * 100
avg_time = total_time / n
print(f"| 子任务拆解准确率 | {avg_task:.1f}% | ≥85% | {'✅' if avg_task >= 85 else '❌'} |")
print(f"| 指标覆盖率 | {avg_ind:.1f}% | ≥80% | {'✅' if avg_ind >= 80 else '❌'} |")
print(f"| 报告结构完整性 | {avg_struct:.1f}% | ≥80% | {'✅' if avg_struct >= 80 else '❌'} |")
print(f"| 端到端平均耗时 | {avg_time:.1f}s | ≤30s | {'✅' if avg_time <= 30 else '❌'} |")
print()

print(f"### 按类别")
print(f"| 类别 | 题数 | 拆解准确率 | 指标覆盖率 | 平均耗时 |")
print(f"|------|:--:|:--:|:--:|:--:|")
for cat in sorted(by_category.keys()):
    g = by_category[cat]
    c = g["count"]
    print(f"| {cat} | {c} | {g['task_score']/c*100:.1f}% | {g['ind_coverage']/c*100:.1f}% | {g['time']/c:.1f}s |")

print(f"\n### 按难度")
print(f"| 难度 | 题数 | 拆解准确率 | 指标覆盖率 | 平均耗时 |")
print(f"|------|:--:|:--:|:--:|:--:|")
for d in ["easy", "medium", "hard"]:
    g = by_difficulty.get(d, {"count": 0, "task_score": 0, "ind_coverage": 0, "time": 0})
    c = g["count"]
    if c > 0:
        print(f"| {d} | {c} | {g['task_score']/c*100:.1f}% | {g['ind_coverage']/c*100:.1f}% | {g['time']/c:.1f}s |")

if failed:
    print(f"\n### 失败题: {failed}")

print(f"\n评测完成 [OK]")
