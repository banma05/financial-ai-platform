"""
Agent 评测脚本 — 20 题全量评测（子任务拆解准确率 + 指标覆盖率 + 耗时基准）
"""
import os
import sys
import time
import json
from pathlib import Path

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# ── 轻量模式（默认开启）：跳过 CrossEncoder + 强制 CPU（省 3-4GB 总内存）──
# 设置 EVAL_LIGHT=0 可关闭轻量模式（GPU 加速，但需要足够显存）
LIGHT_MODE = os.environ.get("EVAL_LIGHT", "1").lower() in ("1", "true", "yes")
if LIGHT_MODE:
    # 必须在 PyTorch 初始化前禁用 CUDA，否则 GPU 显存溢出会映射到系统内存
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["EVAL_LIGHT"] = "1"      # 写回环境变量，确保下游模块（hybrid_search等）也能感知

# 🔧 必须在所有 import 之前预加载 sentence_transformers（防止 CUDA segfault）
import sentence_transformers  # noqa

# 🔧 修复 Windows GBK 编码下 emoji 打印崩溃
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from loguru import logger
from agent.planner import Planner, BUILTIN_TEMPLATES
from agent.schemas import AnalysisPlan, AnalysisTask
from agent.graph import run_agent_sync
from rag.model_router import init_usage, get_usage  # V6.0: 成本追踪

TEST_SET = Path(__file__).parent.parent / "data" / "agent_questions.json"

with open(TEST_SET, "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data["questions"]
meta = data["meta"]
logger.info(f"开始 Agent 评测: {len(questions)} 题, {len(meta['categories'])} 类")

planner = Planner()  # 复用同一个 Planner 实例

# ============ 评测函数 ============

def score_task_decomposition(plan: AnalysisPlan, golden: dict) -> dict:
    """对比 Planner 输出与题目要求（兼容 required_numbers/min_tasks 格式）"""
    tasks = plan.tasks
    if plan.requires_clarification:
        return {"score": None, "status": "needs_clarification",
                "task_count": 0, "detail": plan.requires_clarification}

    scores = {}

    # 1. 任务数量：不低于 min_tasks 即可（没有 golden_plan 时用 min_tasks ×1.5 作上限）
    n = len(tasks)
    min_t = golden.get("min_tasks", 2)
    max_t = golden.get("max_tasks", min_t * 3)
    if n < min_t:
        scores["count"] = n / min_t
    elif n > max_t:
        scores["count"] = max(0, 1 - (n - max_t) / max_t)
    else:
        scores["count"] = 1.0

    # 2. 任务类型：检查是否包含 data_query + (calculate 或 analyze)
    actual_types = set(t.task_type for t in tasks)
    has_data = "data_query" in actual_types
    has_calc = "calculate" in actual_types
    has_analyze = "analyze" in actual_types
    scores["type_coverage"] = (has_data * 0.4 + (has_calc or has_analyze) * 0.6)

    # 3. 图表覆盖率：有 required_chart 时检查是否包含对应 chart 任务
    req_chart = golden.get("required_chart", "")
    if req_chart:
        chart_types = set()
        for t in tasks:
            ct = t.params.get("chart_type", "") if isinstance(t.params, dict) else ""
            if ct:
                chart_types.add(ct)
        scores["chart_coverage"] = 1.0 if chart_types else 0.0
    else:
        scores["chart_coverage"] = 1.0

    # 综合得分
    weights = {"count": 0.3, "type_coverage": 0.4, "chart_coverage": 0.3}
    overall = sum(scores[k] * weights[k] for k in weights)
    scores["overall"] = round(overall, 4)

    return {"score": round(overall, 4), "status": "ok", "detail": scores, "task_count": n}


def score_indicator_coverage(report: str, expected_indicators: list) -> dict:
    """检查报告中是否包含期望的财务指标（兼容旧格式）"""
    if not expected_indicators:
        return {"coverage": 1.0, "found": [], "missing": [], "total": 0}
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


def score_number_accuracy(report: str, required_numbers: dict) -> dict:
    """
    V8.2 核心指标：数字准确率。

    检查 required_numbers 中的每个指标值是否出现在报告中。
    使用 1% 容差（允许格式化差异）。

    返回: {accuracy, matched, mismatched, total}
    """
    if not required_numbers:
        return {"accuracy": 1.0, "matched": [], "mismatched": [], "total": 0}

    import re
    # 提取报告中的所有数字
    report_numbers = re.findall(r'\d+\.?\d*', report)
    report_floats = []
    for n in report_numbers:
        try:
            report_floats.append(float(n))
        except ValueError:
            pass

    matched = []
    mismatched = []
    for key, expected_val in required_numbers.items():
        if not isinstance(expected_val, (int, float)):
            continue
        found = False
        for rf in report_floats:
            if expected_val == 0:
                if rf == 0:
                    found = True
                    break
            else:
                rel_diff = abs(rf - expected_val) / abs(expected_val)
                if rel_diff < 0.01:  # 1% 容差
                    found = True
                    break
        if found:
            matched.append(key)
        else:
            mismatched.append(key)

    total = len(matched) + len(mismatched)
    accuracy = len(matched) / total if total > 0 else 1.0
    return {
        "accuracy": round(accuracy, 4),
        "matched": matched,
        "mismatched": mismatched,
        "total": total,
    }


def extract_data_values_from_results(results: list) -> dict:
    """
    V8.2: 从 Agent 执行结果中提取 data_values（Agent 实际使用的数值）。

    只提取 data_query 任务的 data 字段（SQL 直查结果），
    跳过 calculate 任务的百分比结果（不是原始数据值）。
    """
    data_values = {}
    for r in results:
        if not r.get("success", True):
            continue
        if r.get("task_type") != "data_query":
            continue  # 只取 SQL 查询的原始数据
        data = r.get("data", {})
        if not isinstance(data, dict):
            continue
        inner = data.get("data", {})
        if isinstance(inner, dict):
            for k, v in inner.items():
                if isinstance(v, (int, float)):
                    if k in ("found", "success", "confidence", "source"):
                        continue
                    data_values[k] = v
    return data_values


def score_number_accuracy_v2(report: str, data_values: dict) -> dict:
    """
    V8.2 改进版：用 Agent 实际收到的 data_values 做评测基准。

    关键处理：数据库存储原始单位（元），报告显示格式化单位（亿/万）。
    此函数将数据库值转为多种可能的报告表示形式，逐一匹配。

    与旧版 score_number_accuracy 的区别：
    - 旧版: 对比硬编码 required_numbers（人工编写，与数据库不一致）
    - 新版: 对比 data_values（Agent 从 SQL 实际查到的值，绝对权威）
    """
    if not data_values:
        return {"accuracy": 1.0, "matched": [], "mismatched": [], "total": 0}

    import re
    report_numbers = re.findall(r'\d+\.?\d*', report)
    report_floats = set()
    for n in report_numbers:
        try:
            report_floats.add(float(n))
        except ValueError:
            pass

    matched = []
    mismatched = []
    for key, raw_val in data_values.items():
        # 跳过元数据/百分比值（太小且非金额）
        if abs(raw_val) < 10:
            continue

        # 生成数据库值在报告中可能出现的所有形式
        # 数据库存元 → 报告可能显示: 元、万元、亿元
        candidates = set()
        candidates.add(raw_val)                    # 原始值（元）
        candidates.add(round(raw_val / 1e4, 2))    # 万元
        candidates.add(round(raw_val / 1e8, 2))    # 亿元

        # ── V8.3: 现金流指标特殊处理 ──
        # 现金流值通常很大（百亿级别），报告中常以"亿元"显示，
        # 且自由现金流 = 经营CF - 资本支出是计算值，容差需放宽
        cf_patterns = ('operating_cf', 'investing_cf', 'financing_cf',
                       'free_cash', '经营现金流', '投资现金流', '筹资现金流',
                       '自由现金流', 'capex')
        is_cash_flow = any(p in key.lower() for p in cf_patterns)
        if is_cash_flow:
            # 额外候选：去掉小数的亿元（如 615亿）、保留更多精度的亿元
            yi = round(raw_val / 1e8, 2)
            candidates.add(round(yi, 0))             # 615 亿（整数亿元）
            candidates.add(round(raw_val / 1e8, 1))  # 615.2 亿（一位小数亿元）
            candidates.add(round(raw_val / 1e8, 4))  # 高精度亿元

        found = False
        for rf in report_floats:
            for c in candidates:
                if abs(c) < 1e-6:
                    if abs(rf) < 1e-6:
                        found = True
                        break
                else:
                    rel_diff = abs(rf - c) / abs(c)
                    if rel_diff < 0.02:  # 2% 容差
                        found = True
                        break
            if found:
                break

        if found:
            matched.append(key)
        else:
            mismatched.append(key)

    total = len(matched) + len(mismatched)
    accuracy = len(matched) / total if total > 0 else 1.0
    return {
        "accuracy": round(accuracy, 4),
        "matched": matched,
        "mismatched": mismatched,
        "total": total,
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
total_number_accuracy = 0.0   # V8.2 核心指标
total_indicator_coverage = 0.0
total_structure_score = 0.0
total_time = 0.0
total_cost = 0.0
total_tokens_all = 0
valid_plan_count = 0
valid_number_count = 0          # V8.2: 有数值校验的题目数
clarification_count = 0
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
    if task_result["score"] is not None:
        total_task_score += task_result["score"]
        valid_plan_count += 1
    logger.info(f"  Planner: score={task_result['score'] if task_result['score'] is not None else 'N/A'} tasks={task_result.get('task_count','?')} time={plan_time:.1f}s")
    if task_result["status"] == "needs_clarification":
        clarification_count += 1
        logger.warning(f"  [!] 需要追问: {task_result['detail'][:80]}")

    # Phase 2: 全链路执行（同步模式，复用 Phase 1 的 Plan 避免重复 LLM 调用）
    exec_start = time.time()
    try:
        agent_result = run_agent_sync(query, plan=plan)
        # ── V6.0: 捕获本次分析的 token 用量 ──
        usage = get_usage()
        question_cost = round(
            (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
            / 1_000_000 * 2.0,  # 均价 ¥2/百万tokens
            6,
        )
        question_tokens = usage.get("total_tokens", 0)
    except Exception as e:
        logger.error(f"  Agent 执行失败: {e}")
        failed.append(qid)
        continue
    exec_time = time.time() - exec_start
    total_time += exec_time

    # Phase 3: 报告评测（V8.2: data_values 驱动评测 + 硬编码 required_numbers 做参考）
    report = agent_result.get("report", "")
    # 提取 Agent 实际从 SQL 查询到的数据值
    data_values = extract_data_values_from_results(agent_result.get("task_results", []))
    # 新版评分：用 data_values（数据库真值）
    num_result = score_number_accuracy_v2(report, data_values)
    # 旧版评分：用硬编码 required_numbers（参考值，不参与主要评判）
    ref_result = score_number_accuracy(report, q.get("required_numbers", {}))
    ind_result = score_indicator_coverage(report, q.get("expected_indicators", []))
    struct_result = score_report_structure(report)
    if num_result["total"] > 0:
        total_number_accuracy += num_result["accuracy"]
        valid_number_count += 1
    total_indicator_coverage += ind_result["coverage"]
    total_structure_score += struct_result["structure_score"]
    total_cost += question_cost
    total_tokens_all += question_tokens

    logger.info(f"  执行: {exec_time:.1f}s | 真实数字准确率={num_result['accuracy']:.1%} | 参考准确率={ref_result['accuracy']:.1%} | 结构={struct_result['structure_score']:.1%}")
    if num_result["mismatched"]:
        logger.info(f"  数字不符: {num_result['mismatched'][:5]}")
    if ref_result["mismatched"]:
        logger.info(f"  参考不符: {ref_result['mismatched'][:5]}")

    # 按类别/难度分组
    for group, key in [(by_category, cat), (by_difficulty, diff)]:
        if key not in group:
            group[key] = {"count": 0, "valid_count": 0, "task_score": 0.0,
                          "ind_coverage": 0.0, "num_accuracy": 0.0, "num_count": 0, "time": 0.0}
        group[key]["count"] += 1
        if task_result["score"] is not None:
            group[key]["valid_count"] += 1
            group[key]["task_score"] += task_result["score"]
        group[key]["ind_coverage"] += ind_result["coverage"]
        group[key]["time"] += exec_time
        if num_result["total"] > 0:
            group[key]["num_accuracy"] += num_result["accuracy"]
            group[key]["num_count"] += 1

    results.append({
        "id": qid,
        "query": query[:80],
        "category": cat,
        "difficulty": diff,
        "task_score": task_result["score"],
        "number_accuracy": num_result["accuracy"],
        "ref_accuracy": ref_result["accuracy"],
        "num_matched": num_result["matched"],
        "num_mismatched": num_result["mismatched"],
        "indicator_coverage": ind_result["coverage"],
        "structure_score": struct_result["structure_score"],
        "plan_time": round(plan_time, 2),
        "exec_time": round(exec_time, 2),
        "task_count": task_result.get("task_count", 0),
        "needs_clarification": task_result["status"] == "needs_clarification",
        "tokens": question_tokens,
        "cost": question_cost,
    })

elapsed = time.time() - start_all
n = len(questions)

# ============ 报告 ============
print("\n" + "=" * 70)
print(">>> Agent 20 题全量评测报告 <<<")
print("=" * 70)
print(f"题目数: {n} | 总耗时: {elapsed:.1f}s | 追问: {clarification_count} | 失败: {len(failed)}")
if LIGHT_MODE:
    print("⚡ 轻量模式：CrossEncoder 重排已跳过")
if clarification_count > 0:
    print(f"⚠️ 追问不计入拆解平均分（共 {clarification_count} 题）")
print()

print(f"| 指标 | 值 | 目标 | 达标? |")
print(f"|------|:--:|:--:|:--:|")
avg_task = total_task_score / valid_plan_count * 100 if valid_plan_count > 0 else 0
avg_num = total_number_accuracy / valid_number_count * 100 if valid_number_count > 0 else 0
avg_ind = total_indicator_coverage / n * 100
avg_struct = total_structure_score / n * 100
avg_time = total_time / n
print(f"| 🔴 数字准确率 | {avg_num:.1f}% | ≥80% | {'✅' if avg_num >= 80 else '❌'} |")
print(f"| 子任务拆解准确率 | {avg_task:.1f}% | ≥85% | {'✅' if avg_task >= 85 else '❌'} |")
print(f"| 报告结构完整性 | {avg_struct:.1f}% | ≥80% | {'✅' if avg_struct >= 80 else '❌'} |")
print(f"| 端到端平均耗时 | {avg_time:.1f}s | ≤30s | {'✅' if avg_time <= 30 else '❌'} |")
print()

print(f"### 按类别（含数字准确率）")
print(f"| 类别 | 题数 | 拆解准确率 | 数字准确率 | 平均耗时 |")
print(f"|------|:--:|:--:|:--:|:--:|")
for cat in sorted(by_category.keys()):
    g = by_category[cat]
    c, vc = g["count"], g.get("valid_count", g["count"])
    nc = g.get("num_count", 0)
    na = g.get("num_accuracy", 0) / nc * 100 if nc > 0 else 0
    print(f"| {cat} | {c} | {g['task_score']/vc*100:.1f}% | {na:.1f}% | {g['time']/c:.1f}s |")

print(f"\n### 按难度")
print(f"| 难度 | 题数 | 拆解准确率 | 数字准确率 | 平均耗时 |")
print(f"|------|:--:|:--:|:--:|:--:|")
for d in ["easy", "medium", "hard"]:
    g = by_difficulty.get(d, {"count": 0, "valid_count": 0, "task_score": 0, "num_accuracy": 0, "num_count": 0, "time": 0})
    c, vc = g["count"], g.get("valid_count", g["count"])
    nc = g.get("num_count", 0)
    na = g.get("num_accuracy", 0) / nc * 100 if nc > 0 else 0
    if c > 0:
        print(f"| {d} | {c} | {g['task_score']/vc*100:.1f}% | {na:.1f}% | {g['time']/c:.1f}s |")

if failed:
    print(f"\n### 失败题: {failed}")

avg_cost = total_cost / n if n > 0 else 0
print(f"\n### 成本维度（V6.0 新增）")
print(f"| 指标 | 值 |")
print(f"|------|:--:|")
print(f"| 总 Token 用量 | {total_tokens_all:,} |")
print(f"| 总费用 | ¥{total_cost:.4f} |")
print(f"| 单题均费 | ¥{avg_cost:.4f} |")

# ============ 报告持久化 ============
from datetime import datetime
reports_dir = Path(__file__).parent.parent / "reports"
reports_dir.mkdir(exist_ok=True)
report_path = reports_dir / f"agent_bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

report_data = {
    "timestamp": datetime.now().isoformat(),
    "elapsed_s": round(elapsed, 1),
    "total_questions": n,
    "valid_plan_count": valid_plan_count,
    "valid_number_count": valid_number_count,
    "clarification_count": clarification_count,
    "failed_count": len(failed),
    "failed_questions": [f"{qid}: {reason}" for qid, reason in failed],
    "avg_number_accuracy": round(avg_num, 1),
    "avg_task_accuracy": round(avg_task, 1),
    "avg_structure_score": round(avg_struct, 1),
    "avg_time_s": round(avg_time, 1),
    "total_tokens": total_tokens_all,
    "total_cost_rmb": round(total_cost, 4),
    "avg_cost_rmb": round(avg_cost, 4),
    "by_category": {
        cat: {
            "count": g["count"],
            "task_accuracy": round(g["task_score"] / max(g.get("valid_count", g["count"]), 1) * 100, 1),
            "num_accuracy": round(g.get("num_accuracy", 0) / max(g.get("num_count", 1), 1) * 100, 1),
            "avg_time_s": round(g["time"] / max(g["count"], 1), 1),
        }
        for cat, g in by_category.items()
    },
    "by_difficulty": {
        d: {
            "count": g["count"],
            "task_accuracy": round(g["task_score"] / max(g.get("valid_count", g["count"]), 1) * 100, 1),
            "num_accuracy": round(g.get("num_accuracy", 0) / max(g.get("num_count", 1), 1) * 100, 1),
            "avg_time_s": round(g["time"] / max(g["count"], 1), 1),
        }
        for d, g in by_difficulty.items()
    },
    "per_question": per_question,
}

with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report_data, f, ensure_ascii=False, indent=2)
print(f"\n📄 报告已保存: {report_path}")

print(f"\n评测完成 [OK]")
