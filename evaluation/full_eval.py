"""
全量评测入口 — 一键跑 RAG + Agent + MCP 三项评测

用法:
    python evaluation/full_eval.py              # 跑全部
    python evaluation/full_eval.py --rag         # 只跑 RAG
    python evaluation/full_eval.py --agent       # 只跑 Agent
    python evaluation/full_eval.py --mcp         # 只跑 MCP

输出: 统一汇总表 + JSON 报告写入 evaluation/reports/
"""
import os
import sys
import json
import time
import subprocess
import argparse
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
EVAL_DIR = Path(__file__).parent
REPORTS_DIR = EVAL_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# 轻量模式环境变量
_light_mode = os.environ.get("EVAL_LIGHT", "").lower() in ("1", "true", "yes")


def _subprocess_env():
    """构造子进程环境变量，轻量模式下添加 EVAL_LIGHT"""
    env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "backend")}
    if _light_mode:
        env["EVAL_LIGHT"] = "1"
    return env


def run_rag_eval() -> dict:
    """运行 RAG 50 题评测"""
    print("\n" + "=" * 60)
    print("📚 模块一：RAG 检索评测")
    print("=" * 60)
    start = time.time()
    result = subprocess.run(
        [sys.executable, str(EVAL_DIR / "rag" / "quick_eval.py")],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, timeout=600,
        env=_subprocess_env(),
    )
    elapsed = time.time() - start
    print(result.stdout)
    if result.stderr:
        # 过滤掉 jieba/warning 噪音
        errors = [l for l in result.stderr.split("\n")
                  if l and "UserWarning" not in l and "pkg_resources" not in l]
        if errors:
            print("⚠️  stderr:", "\n".join(errors[-5:]))
    return {
        "module": "RAG",
        "elapsed_s": round(elapsed, 1),
        "exit_code": result.returncode,
        "output_tail": result.stdout.split("\n")[-20:] if result.returncode == 0 else [],
    }


def run_agent_eval() -> dict:
    """运行 Agent 20 题评测"""
    print("\n" + "=" * 60)
    print("🤖 模块二：Agent 子任务拆解评测")
    print("=" * 60)
    start = time.time()
    result = subprocess.run(
        [sys.executable, str(EVAL_DIR / "agent" / "bench_agent.py")],
        cwd=str(PROJECT_ROOT),
        capture_output=True, text=True, timeout=900,
        env=_subprocess_env(),
    )
    elapsed = time.time() - start
    print(result.stdout)
    if result.stderr:
        errors = [l for l in result.stderr.split("\n")
                  if l and "UserWarning" not in l and "pkg_resources" not in l]
        if errors:
            print("⚠️  stderr:", "\n".join(errors[-5:]))
    return {
        "module": "Agent",
        "elapsed_s": round(elapsed, 1),
        "exit_code": result.returncode,
        "output_tail": result.stdout.split("\n")[-20:] if result.returncode == 0 else [],
    }


def run_mcp_eval() -> dict:
    """运行 MCP 工具冒烟测试（调用全部 6 个工具的 Mock 数据）"""
    print("\n" + "=" * 60)
    print("🔧 模块三：MCP 工具可用性检查")
    print("=" * 60)
    start = time.time()

    # 直接内联测试，不依赖外部脚本（MCP 暂无独立评测脚本）
    sys.path.insert(0, str(PROJECT_ROOT / "backend"))
    from mcp import (
        StockPriceTool, FinancialStatementsTool, CalculateRatioTool,
        IndustryComparisonTool, MarketIndexTool, FinancialCalendarTool,
    )

    tools = {
        "stock_price": StockPriceTool(),
        "financial_statements": FinancialStatementsTool(),
        "calculate_ratio": CalculateRatioTool(),
        "industry_comparison": IndustryComparisonTool(),
        "market_index": MarketIndexTool(),
        "financial_calendar": FinancialCalendarTool(),
    }

    results = {}
    passed = 0
    for name, tool in tools.items():
        try:
            r = tool.run(symbol="600519")
            ok = r.get("success", False)
            if ok:
                passed += 1
            results[name] = {"ok": ok, "summary": r.get("summary", "")[:80]}
            print(f"  {'✅' if ok else '⚠️'} {name}: {r.get('summary', str(r))[:80]}")
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)[:100]}
            print(f"  ❌ {name}: {e}")

    elapsed = time.time() - start
    print(f"\n  MCP 工具可用: {passed}/{len(tools)}")

    return {
        "module": "MCP",
        "elapsed_s": round(elapsed, 1),
        "exit_code": 0 if passed == len(tools) else 1,
        "detail": {"passed": passed, "total": len(tools), "results": results},
    }


def print_summary(rag: dict, agent: dict, mcp: dict, total_s: float):
    """打印统一汇总表"""
    print("\n" + "=" * 60)
    print(">>> 三模块全量评测汇总 <<<")
    print("=" * 60)
    print(f"评测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {total_s:.0f}s")
    print()

    def status_icon(code):
        return "✅" if code == 0 else "❌"

    print(f"| 模块 | 状态 | 耗时 | 关键输出 |")
    print(f"|------|:--:|:--:|------|")
    for r in [rag, agent, mcp]:
        key = ""
        if r["module"] == "MCP" and "detail" in r:
            key = f"{r['detail']['passed']}/{r['detail']['total']} 工具可用"
        elif r["output_tail"]:
            # 提取最后一行有意义的数据行
            for ln in reversed(r["output_tail"]):
                ln = ln.strip()
                if ln and not ln.startswith("=") and not ln.startswith("-"):
                    key = ln[:100]
                    break
        print(f"| {r['module']} | {status_icon(r['exit_code'])} | {r['elapsed_s']}s | {key} |")

    # 写 JSON 报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "total_elapsed_s": round(total_s, 1),
        "rag": {"exit_code": rag["exit_code"], "elapsed_s": rag["elapsed_s"]},
        "agent": {"exit_code": agent["exit_code"], "elapsed_s": agent["elapsed_s"]},
        "mcp": {"exit_code": mcp["exit_code"], "elapsed_s": mcp["elapsed_s"],
                "detail": mcp.get("detail", {})},
    }
    report_path = REPORTS_DIR / f"full_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 报告已保存: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="三模块全量评测")
    parser.add_argument("--rag", action="store_true", help="仅 RAG")
    parser.add_argument("--agent", action="store_true", help="仅 Agent")
    parser.add_argument("--mcp", action="store_true", help="仅 MCP")
    parser.add_argument("--light", action="store_true",
                        help="轻量模式：跳过 CrossEncoder 重排，省 2-3GB 内存")
    args = parser.parse_args()

    run_all = not (args.rag or args.agent or args.mcp)

    # ── 轻量模式：设置环境变量供子进程和 hybrid_search 内部检查 ──
    global _light_mode
    if args.light:
        _light_mode = True
        os.environ["EVAL_LIGHT"] = "1"
        print("⚡ 轻量模式已启用：将跳过 CrossEncoder 重排，省 2-3GB 内存\n")

    results = {}
    total_start = time.time()

    if run_all or args.rag:
        results["rag"] = run_rag_eval()
    else:
        results["rag"] = {"module": "RAG", "elapsed_s": 0, "exit_code": -1, "output_tail": []}

    if run_all or args.agent:
        results["agent"] = run_agent_eval()
    else:
        results["agent"] = {"module": "Agent", "elapsed_s": 0, "exit_code": -1, "output_tail": []}

    if run_all or args.mcp:
        results["mcp"] = run_mcp_eval()
    else:
        results["mcp"] = {"module": "MCP", "elapsed_s": 0, "exit_code": -1, "output_tail": []}

    total_s = time.time() - total_start
    print_summary(results["rag"], results["agent"], results["mcp"], total_s)


if __name__ == "__main__":
    main()
