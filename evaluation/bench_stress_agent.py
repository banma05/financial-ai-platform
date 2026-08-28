"""
Agent 完整分析压力测试 — 并发提交真实分析请求，测吞吐/延迟/成功率

与 50 题评测（进程内 run_agent_sync）不同，压测走真实 HTTP API（FastAPI + 中间件 +
鉴权 + 限流），能反映生产链路（含 GIL 竞争、连接池、模型共享）在并发下的表现。

用法:
    # 1) 先启动后端
    #    cd D:\\实战项目\\financial-ai-platform
    #    source ../.venv/Scripts/activate
    #    python -m backend.main
    # 2) 再跑压测
    python evaluation/bench_stress_agent.py --concurrency 4 --timeout 120

输出:
    控制台汇总表 + evaluation/reports/stress_agent_YYYYMMDD_HHMMSS.json

指标:
    成功率 / 端到端耗时(min/avg/max/P50/P95) / 服务端processing_time /
    任务数 / 报告+图表完整性 / token/费用(通过 /api/v1/admin/stats/cost 差值估算)
"""
import os
import sys
import json
import time
import argparse
import statistics
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv

# 加载项目 .env（含 API_KEY 鉴权密钥）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
API_KEY = os.getenv("API_KEY", "")
HEADERS = {"X-API-Key": API_KEY} if API_KEY else {}

API_ANALYZE = "http://localhost:8001/api/v1/agent/analyze"
API_HEALTH = "http://localhost:8001/health"
API_COST = "http://localhost:8001/api/v1/admin/stats/cost"


def load_queries(limit: int) -> list:
    """从评测集选多样化的代表性题目（模板/自由拆解/RAG/非RAG 混合）。"""
    qpath = Path(__file__).parent / "data" / "agent_questions_v9.json"
    with open(qpath, "r", encoding="utf-8") as f:
        data = json.load(f)
    questions = [q for q in data["questions"] if isinstance(q, dict)]

    selected, seen = [], set()
    for q in questions:
        is_tpl = q.get("category", "") != "自由拆解"
        rag = q.get("has_rag", False)
        key = f"{'tpl' if is_tpl else 'free'}_{'rag' if rag else 'sql'}"
        if key not in seen:
            seen.add(key)
            selected.append(q)
        if len(selected) >= limit:
            break
    return selected


def preflight() -> bool:
    """健康检查，确认后端已启动。"""
    try:
        r = requests.get(API_HEALTH, timeout=5, headers=HEADERS)
        ok = r.status_code == 200 and r.json().get("status") == "ok"
        print(f"  [{r.status_code}] {API_HEALTH} -> {r.json()}" if ok else f"  [!] 健康检查异常: {r.text[:100]}")
        return ok
    except Exception as e:
        print(f"  [!] 后端未启动或不可达: {e}")
        return False


def fetch_cost() -> float:
    """从平台 Token 记账接口读取累计费用（¥）。"""
    try:
        r = requests.get(API_COST, timeout=10, headers=HEADERS)
        if r.status_code == 200:
            return float(r.json().get("total_cost", 0) or 0)
    except Exception:
        pass
    return -1.0


def run_one(q: dict, timeout: int) -> dict:
    """单次并发请求：测量端到端耗时，检查响应完整性。"""
    payload = {"query": q["query"], "session_id": f"stress-{q['id']}"}
    wall_start = time.perf_counter()
    try:
        resp = requests.post(API_ANALYZE, json=payload, timeout=timeout, headers=HEADERS)
        wall = time.perf_counter() - wall_start
        if resp.status_code != 200:
            return {"qid": q["id"], "ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:120]}", "wall_s": round(wall, 2)}
        data = resp.json()
        return {
            "qid": q["id"],
            "query": q["query"][:50],
            "ok": True,
            "wall_s": round(wall, 2),
            "processing_time_s": round(float(data.get("processing_time", 0)), 2),
            "task_count": data.get("task_count", 0),
            "report_len": len(data.get("report", "")),
            "chart_count": len(data.get("chart_options", [])),
            "clarification": data.get("clarification"),
        }
    except Exception as e:
        wall = time.perf_counter() - wall_start
        return {"qid": q["id"], "ok": False, "error": str(e)[:120], "wall_s": round(wall, 2)}


def pct(vals: list, p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(len(s) * p / 100)))
    return s[idx]


def main():
    parser = argparse.ArgumentParser(description="Agent 完整分析压力测试")
    parser.add_argument("--concurrency", type=int, default=4, help="并发请求数（默认4）")
    parser.add_argument("--timeout", type=int, default=120, help="单请求超时秒数（默认120）")
    parser.add_argument("--skip-health", action="store_true", help="跳过健康检查")
    args = parser.parse_args()

    print("=" * 70)
    print(f">>> Agent 完整分析压力测试 <<<  (并发 {args.concurrency}, 超时 {args.timeout}s)")
    print("=" * 70)

    if not args.skip_health:
        if not preflight():
            sys.exit(1)

    queries = load_queries(args.concurrency)
    print(f"压测题目: {len(queries)} 题")
    for q in queries:
        print(f"  - {q['id']} [{q.get('category','?')}] {q['query'][:40]}...")

    cost_before = fetch_cost()
    print(f"压测前累计费用: {'¥'+format(cost_before,'.4f') if cost_before >= 0 else '无法读取'}")

    # ── 并发提交 ──
    results = []
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(run_one, q, args.timeout): q for q in queries}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            mark = "✅" if r["ok"] else "❌"
            if r["ok"]:
                print(f"  {mark} {r['qid']} 端到端{r['wall_s']}s 服务端{r['processing_time_s']}s "
                      f"任务{r['task_count']} 图表{r['chart_count']} 报告{r['report_len']}字")
            else:
                print(f"  {mark} {r['qid']} 失败: {r.get('error','?')}")
    total_wall = time.perf_counter() - start

    cost_after = fetch_cost()
    cost_delta = (cost_after - cost_before) if (cost_after >= 0 and cost_before >= 0) else -1.0

    # ── 统计 ──
    ok_list = [r for r in results if r["ok"]]
    walls = [r["wall_s"] for r in ok_list]
    procs = [r["processing_time_s"] for r in ok_list if r["ok"]]
    success = len(ok_list) / len(results) if results else 0
    chart_ok = sum(1 for r in ok_list if r.get("chart_count", 0) > 0)
    report_ok = sum(1 for r in ok_list if r.get("report_len", 0) > 500)

    print("\n" + "=" * 70)
    print(">>> 压测结果汇总 <<<")
    print("=" * 70)
    print(f"并发数:        {args.concurrency}")
    print(f"请求总数:      {len(results)} | 成功: {len(ok_list)} | 失败: {len(results)-len(ok_list)}")
    print(f"成功率:        {success*100:.1f}%")
    if ok_list:
        print(f"端到端耗时(客户端): min={min(walls):.1f}s avg={statistics.mean(walls):.1f}s "
              f"max={max(walls):.1f}s | P50={pct(walls,50):.1f}s P95={pct(walls,95):.1f}s")
        print(f"服务端处理耗时:     min={min(procs):.1f}s avg={statistics.mean(procs):.1f}s "
              f"max={max(procs):.1f}s")
    print(f"总墙钟:        {total_wall:.1f}s（并发重叠）")
    print(f"报告完整性:    {report_ok}/{len(ok_list)} 题返回完整报告(>500字)")
    print(f"图表完整性:    {chart_ok}/{len(ok_list)} 题返回图表")
    if cost_delta >= 0:
        print(f"压测LLM费用:    ¥{cost_delta:.4f} (平均 ¥{cost_delta/max(len(ok_list),1):.4f}/题)")
    else:
        print(f"压测LLM费用:    无法读取（Token记账接口不可用）")

    # ── 保存报告 ──
    report = {
        "timestamp": datetime.now().isoformat(),
        "type": "stress_agent",
        "config": {"concurrency": args.concurrency, "timeout": args.timeout},
        "summary": {
            "total": len(results), "success": len(ok_list), "failed": len(results) - len(ok_list),
            "success_rate": round(success, 4),
            "end_to_end_s": {"min": round(min(walls),2) if walls else None,
                             "avg": round(statistics.mean(walls),2) if walls else None,
                             "max": round(max(walls),2) if walls else None,
                             "p50": round(pct(walls,50),2) if walls else None,
                             "p95": round(pct(walls,95),2) if walls else None},
            "server_time_s": {"avg": round(statistics.mean(procs),2) if procs else None},
            "total_wall_s": round(total_wall, 2),
            "report_ok": report_ok, "chart_ok": chart_ok,
            "cost_rmb": round(cost_delta, 4) if cost_delta >= 0 else None,
        },
        "details": results,
    }
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / f"stress_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 压测报告已保存: {path}")


if __name__ == "__main__":
    main()
