"""
V8.0 分层评测运行器

用法:
    python evaluation/v8_bench.py --layer sql     # 仅 SQL 层 (20题, 零LLM)
    python evaluation/v8_bench.py --layer agent   # Agent 层 (15题, 需LLM)
    python evaluation/v8_bench.py --layer rag     # RAG 层 (15题, 需ChromaDB)
    python evaluation/v8_bench.py --all           # 全量 50 题

输出: 控制台报告 + evaluation/reports/v8_bench_{timestamp}.json
"""
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ.setdefault("EVAL_LIGHT", "1")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

# 🔧 Windows GBK emoji 修复
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

DATA_DIR = Path(__file__).parent / "data"
REPORT_DIR = Path(__file__).parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

TOLERANCE_PCT = {"sql": 2, "agent": 5}  # sql 容忍 2%, agent 容忍 5%


# ==================== SQL 层评测 ====================

def evaluate_sql() -> dict:
    """20 题 SQL 查询评测"""
    import db.financial_models  # noqa
    from db.financial_query import try_query

    with open(DATA_DIR / "sql_questions.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data["questions"]
    results = []
    total_hits = 0
    total_expected = 0
    total_accurate = 0
    avg_latency = 0

    for q in questions:
        start = time.perf_counter()
        result = try_query(q["query"])
        latency_ms = (time.perf_counter() - start) * 1000

        expected = q.get("expected_values", {})
        tolerance = q.get("tolerance_pct", TOLERANCE_PCT["sql"])
        data_dict = result.get("data", {}) if result else {}

        # 统计预期值命中情况
        hits = {}
        for key, expected_val in expected.items():
            found = False
            accurate = False
            for dk, dv in data_dict.items():
                if key in dk or dk in key:  # 模糊匹配键名
                    found = True
                    if expected_val and dv:
                        # 单位统一：expected 是亿（< 10^6），SQL 返回元（> 10^6）
                        sql_val = dv / 1e8 if abs(dv) > 1e6 else dv
                        pct_diff = abs(sql_val - expected_val) / abs(expected_val) * 100
                        accurate = pct_diff <= tolerance
                        hits[key] = {"found": True, "accurate": accurate,
                                     "expected": expected_val, "got": round(sql_val, 2),
                                     "diff_pct": round(pct_diff, 1)}
                    else:
                        hits[key] = {"found": True, "accurate": True,
                                     "expected": expected_val, "got": dv}
                    break
            if not found:
                hits[key] = {"found": False, "accurate": False,
                             "expected": expected_val, "got": None}

        hit_count = sum(1 for h in hits.values() if h["found"])
        acc_count = sum(1 for h in hits.values() if h["accurate"])
        total_hits += hit_count
        total_expected += len(expected)
        total_accurate += acc_count
        avg_latency += latency_ms

        results.append({
            "id": q["id"],
            "query": q["query"],
            "expected_count": len(expected),
            "hits": hit_count,
            "accurate": acc_count,
            "latency_ms": round(latency_ms, 1),
            "details": hits,
        })

    avg_latency /= len(questions)

    return {
        "layer": "SQL",
        "total_questions": len(questions),
        "coverage": f"{total_hits}/{total_expected} = {total_hits/max(total_expected,1)*100:.1f}%",
        "accuracy": f"{total_accurate}/{total_expected} = {total_accurate/max(total_expected,1)*100:.1f}%",
        "avg_latency_ms": round(avg_latency, 1),
        "results": results,
    }


# ==================== Agent 层评测 ====================

def evaluate_agent(light: bool = True) -> dict:
    """15 题 Agent 端到端评测"""
    from agent.planner import Planner
    from agent.executor import Executor, ToolRegistry
    from agent.graph import run_agent_sync
    from agent.tools.data_query import DataQueryTool
    from agent.tools.financial_calc import FinancialCalcTool
    from agent.tools.chart import ChartTool
    import db.financial_models  # noqa

    with open(DATA_DIR / "agent_questions.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data["questions"]
    if light:
        questions = questions[:5]  # 轻量模式只跑 5 题

    results = []
    planner = Planner()
    registry = ToolRegistry()
    registry.register(DataQueryTool())
    registry.register(FinancialCalcTool())
    registry.register(ChartTool())

    for q in questions:
        start = time.perf_counter()
        try:
            plan = planner.plan(q["query"], template=q.get("template"))
            agent_result = run_agent_sync(q["query"], plan=plan)
            elapsed = round(time.perf_counter() - start, 1)
        except Exception as e:
            agent_result = {"report": str(e), "charts": [], "task_count": 0,
                           "processing_time": round(time.perf_counter() - start, 1)}
            elapsed = agent_result["processing_time"]

        # 检查 required_numbers 是否出现在报告中
        required = q.get("required_numbers", {})
        report = agent_result.get("report", "")
        found_numbers = 0
        number_details = {}
        for key, expected_val in required.items():
            found = False
            # 在报告中查找该数值
            if isinstance(expected_val, float):
                # 转换为多种格式搜索
                variants = [
                    f"{expected_val:.2f}", f"{expected_val:.1f}",
                    f"{expected_val*100:.0f}", f"{expected_val:.0f}",
                ]
                for v in variants:
                    if v in report:
                        found = True
                        break
            number_details[key] = found
            if found:
                found_numbers += 1

        task_count = agent_result.get("task_count", 0)
        chart_count = len(agent_result.get("charts", []))

        results.append({
            "id": q["id"],
            "query": q["query"],
            "category": q["category"],
            "difficulty": q["difficulty"],
            "elapsed_s": elapsed,
            "task_count": task_count,
            "chart_count": chart_count,
            "numbers_found": f"{found_numbers}/{len(required)}",
            "number_details": number_details,
            "report_length": len(report),
        })

    total = sum(r["elapsed_s"] for r in results)
    success_count = sum(1 for r in results if r["numbers_found"].split("/")[0] != "0")

    return {
        "layer": "Agent" + (" (light×5)" if light else " (full×15)"),
        "total_questions": len(questions),
        "avg_elapsed_s": round(total / len(questions), 1),
        "min_elapsed_s": min(r["elapsed_s"] for r in results),
        "max_elapsed_s": max(r["elapsed_s"] for r in results),
        "report_rate": f"{success_count}/{len(questions)}",
        "results": results,
    }


# ==================== CLI ====================

if __name__ == "__main__":
    layer = "sql"
    if "--layer" in sys.argv:
        layer = sys.argv[sys.argv.index("--layer") + 1]
    light = "--light" in sys.argv or os.environ.get("EVAL_LIGHT", "1") == "1"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORT_DIR / f"v8_bench_{timestamp}.json"

    if layer == "sql":
        result = evaluate_sql()
    elif layer == "agent":
        result = evaluate_agent(light=light)
    elif layer == "rag":
        result = {"layer": "RAG", "status": "skipped — needs ChromaDB + rebuilt index"}
    else:
        print(f"Unknown layer: {layer}")
        sys.exit(1)

    # 打印报告
    print(f"\n{'='*60}")
    print(f"V8.0 {result['layer']} 评测报告")
    print(f"{'='*60}")
    for k, v in result.items():
        if k not in ("results",):
            print(f"  {k}: {v}")

    if "results" in result and result["results"]:
        print(f"\n  --- 逐题结果 ---")
        for r in result["results"]:
            status = "OK" if r.get("accurate", r.get("elapsed_s", 99) < 10) else "CHECK"
            if "expected_count" in r:
                print(f"  {r['id']} {status}: hits={r['hits']}/{r['expected_count']}, "
                      f"acc={r['accurate']}, {r['latency_ms']:.0f}ms | {r['query'][:40]}")
            else:
                print(f"  {r['id']} {status}: {r['elapsed_s']}s, "
                      f"nums={r.get('numbers_found','?')}, "
                      f"tasks={r.get('task_count','?')} | {r['query'][:40]}")

    # 保存 JSON
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n报告已保存: {report_path}")
