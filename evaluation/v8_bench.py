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
    in_scope_hits = in_scope_expected = in_scope_accurate = 0
    all_hits = all_expected = all_accurate = 0
    avg_latency = 0

    for q in questions:
        support = q.get("expected_support", "full")
        start = time.perf_counter()
        result = try_query(q["query"])
        latency_ms = (time.perf_counter() - start) * 1000

        expected = q.get("expected_values", {})
        tolerance = q.get("tolerance_pct", TOLERANCE_PCT["sql"])
        data_dict = result.get("data", {}) if result else {}

        # 统计预期值命中情况（根因已修：数据键名不再有 "净利"/"净利率" 歧义）
        # 匹配策略：直接相等 > 双向子串 > 部件交叉匹配
        hits = {}
        for key, expected_val in expected.items():
            key_parts = key.split('_')
            found = False
            accurate = False

            for dk, dv in data_dict.items():
                dk_parts = dk.split('_')

                # 策略1: 直接相等
                match = (key == dk)

                # 策略2: 双向子串
                if not match:
                    match = (key in dk or dk in key)

                # 策略3: 拆成部件后交叉匹配（所有部件互相包含）
                if not match and len(key_parts) >= 2 and len(dk_parts) >= 2:
                    match = all(
                        any(kp in dp for dp in dk_parts) or any(dp in kp for dp in dk_parts)
                        for kp in key_parts
                    )

                if match:
                    found = True
                    if expected_val and dv:
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
        all_hits += hit_count
        all_expected += len(expected)
        all_accurate += acc_count
        if support == "full":
            in_scope_hits += hit_count
            in_scope_expected += len(expected)
            in_scope_accurate += acc_count
        avg_latency += latency_ms

        results.append({
            "id": q["id"],
            "query": q["query"],
            "support": support,
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
        "in_scope_coverage": f"{in_scope_hits}/{in_scope_expected} = {in_scope_hits/max(in_scope_expected,1)*100:.1f}%",
        "in_scope_accuracy": f"{in_scope_accurate}/{in_scope_expected} = {in_scope_accurate/max(in_scope_expected,1)*100:.1f}%",
        "overall_coverage": f"{all_hits}/{all_expected} = {all_hits/max(all_expected,1)*100:.1f}%",
        "overall_accuracy": f"{all_accurate}/{all_expected} = {all_accurate/max(all_expected,1)*100:.1f}%",
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
            plan = planner.plan(q["query"], template_name=q.get("template"))
            agent_result = run_agent_sync(q["query"], plan=plan)
            elapsed = round(time.perf_counter() - start, 1)
        except Exception as e:
            agent_result = {"report": str(e), "charts": [], "task_count": 0,
                           "processing_time": round(time.perf_counter() - start, 1)}
            elapsed = agent_result["processing_time"]

        # 检查 required_numbers 是否出现在报告中（多种格式）
        required = q.get("required_numbers", {})
        report = agent_result.get("report", "")
        found_numbers = 0
        number_details = {}
        for key, expected_val in required.items():
            found = False
            if isinstance(expected_val, (int, float)):
                # 多种格式尝试匹配
                variants = [
                    f"{expected_val:.2f}", f"{expected_val:.1f}",
                    f"{expected_val:.0f}", f"{int(expected_val)}",
                ]
                # 百分比场景：50.56% 在报告里可能是 "50.46%"（计算误差），
                # 用 ±2% 容差做数值比对
                for v in variants:
                    if v in report:
                        found = True
                        break
                # 数值容差回退：在报告中查找 < 2% 误差的数值
                if not found and expected_val > 0:
                    import re as _re
                    for m in _re.finditer(r'(\d+\.?\d*)', report):
                        try:
                            rv = float(m.group(1))
                            for rn in (rv, rv * 100, rv / 100):
                                if abs(rn - expected_val) / abs(expected_val) < 0.02:
                                    found = True
                                    break
                        except ValueError:
                            pass
                        if found:
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


# ==================== RAG 层评测 ====================

def evaluate_rag() -> dict:
    """15 题 RAG 端到端评测：检索 + LLM 生成答案 + 来源引用检查"""
    from rag.retriever import rag_query

    with open(DATA_DIR / "rag_questions.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data["questions"]
    results = []
    total_sources = found_sources = 0
    total_latency = 0.0

    for q in questions:
        start = time.perf_counter()
        try:
            result = rag_query(q["query"], top_k=5)
            elapsed = round(time.perf_counter() - start, 1)
            answer = result.get("answer", "")
            sources = result.get("sources", [])

            # 评分维度
            source_count = len(sources)
            min_required = q.get("min_sources", 1)
            sources_ok = source_count >= min_required

            # 答案质量（基础检查）
            has_citation = "[^" in answer  # 引用标记
            answer_len = len(answer)
            too_short = answer_len < 50
            hallucination_phrase = "文档中未找到" in answer

            total_sources += source_count
            if sources_ok:
                found_sources += 1
            total_latency += elapsed

            results.append({
                "id": q["id"],
                "query": q["query"],
                "category": q.get("category", ""),
                "difficulty": q.get("difficulty", ""),
                "elapsed_s": elapsed,
                "sources_found": source_count,
                "sources_min": min_required,
                "sources_ok": sources_ok,
                "answer_len": answer_len,
                "has_citation": has_citation,
                "hallucination_phrase": hallucination_phrase,
            })
        except Exception as e:
            elapsed = round(time.perf_counter() - start, 1)
            results.append({
                "id": q["id"],
                "query": q["query"],
                "elapsed_s": elapsed,
                "sources_found": 0,
                "sources_min": q.get("min_sources", 1),
                "sources_ok": False,
                "error": str(e)[:100],
            })

    total = len(questions)
    source_rate = f"{found_sources}/{total}"

    return {
        "layer": "RAG",
        "total_questions": total,
        "avg_elapsed_s": round(total_latency / max(total, 1), 1),
        "source_qualify_rate": source_rate,
        "avg_sources_per_q": round(total_sources / max(total, 1), 1),
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
        result = evaluate_rag()
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
        print(f"\n  --- 逐题结果 (F=full P=partial N=none) ---")
        for r in result["results"]:
            support_tag = r.get("support", "?")
            status = "OK" if r.get("accurate", r.get("elapsed_s", 99) < 10) else "CHK"
            if "expected_count" in r:
                print(f"  {r['id']} {status}: hits={r['hits']}/{r['expected_count']}, "
                      f"acc={r['accurate']}, {r['latency_ms']:.0f}ms | {r['query'][:40]}")
            elif "sources_found" in r:
                src_ok = "OK" if r.get("sources_ok") else "LOW"
                err = r.get("error", "")
                print(f"  {r['id']} {src_ok}: sources={r['sources_found']}/{r.get('sources_min','?')}, "
                      f"{r['elapsed_s']}s{', err='+err if err else ''} | {r['query'][:40]}")
            else:
                print(f"  {r['id']} {status}: {r['elapsed_s']}s, "
                      f"nums={r.get('numbers_found','?')}, "
                      f"tasks={r.get('task_count','?')} | {r['query'][:40]}")

    # 保存 JSON
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n报告已保存: {report_path}")
