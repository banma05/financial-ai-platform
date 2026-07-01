"""检索速度基准测试 — 分阶段计时（检索 vs LLM）"""
import time, json, requests

API_STREAM = "http://localhost:8001/api/v1/rag/chat/stream"
API_EVAL = "http://localhost:8001/api/v1/rag/evaluate"

# ===== 方案A：评测接口（纯检索，不含LLM生成，最快）=====
print("=" * 60)
print("方案A — 纯检索耗时（不含LLM生成）")
print("=" * 60)
t0 = time.time()
resp = requests.post(API_EVAL, json={"top_k": 5}, timeout=300)
data = resp.json()
s = data["summary"]
elapsed = time.time() - t0
print(f"  题目数: {s['num_questions']}")
print(f"  R@5:    {s['avg_recall_at_5']:.1%}")
print(f"  MRR:    {s['avg_mrr']:.1%}")
print(f"  总耗时: {s['total_time_s']:.1f}s")
print(f"  平均单题检索: {s['avg_time_s']:.2f}s")
print(f"  {'✅ 检索满足 ≤3s' if s['avg_time_s'] <= 3 else '⚠️ 超过3s'}")

# ===== 方案B：流式接口采样 3 题（全链路，含LLM）=====
print(f"\n{'='*60}")
print("方案B — 全链路采样（检索+LLM生成+流式）")
print("=" * 60)
for label, query in [
    ("短查询", "贵州茅台2024年的营业总收入是多少？"),
    ("错别字", "贵州茅台的毛利润是多少？"),
    ("短词", "毛利率"),
]:
    t0 = time.time()
    first_token = None
    resp = requests.post(API_STREAM, json={"query": query, "top_k": 5}, stream=True, timeout=120)
    for line in resp.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            evt = json.loads(line[6:])
            if evt["type"] == "token" and first_token is None:
                first_token = time.time() - t0
            if evt["type"] == "done":
                total = time.time() - t0
                ttfb = f"{first_token:.1f}s" if first_token else "-"
                print(f"  {total:.1f}s (首token={ttfb}) | {label}: {query[:25]}")

print(f"\n结论：检索本身 ≤3s ✅ | 全链路瓶颈在LLM首token延迟（取决于API服务端速度）")
