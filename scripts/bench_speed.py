"""检索耗时基准测试"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from rag.query_processor import process_query
from rag.hybrid_search import hybrid_search

TEST_QUERIES = [
    ("Q正常-短", "贵州茅台2024年的营业总收入是多少？"),
    ("Q正常-中", "茅台2024年的营业收入相比2023年增长了多少？"),
    ("Q脏数据-错别字", "贵州茅台的毛利润是多少？"),
    ("Q脏数据-中英混杂", "2024年BYD的revenue growth rate是多少percent？"),
    ("Q边界-超短", "毛利率"),
    ("Q边界-超长", "请问腾讯2024年的网络游戏收入有多少？元宇宙相关的布局有哪些？AI大模型方面的投入和进展如何？"),
    ("Q边界-模糊", "它去年赚了多少？"),
    ("Q密集短问", "茅台2024年营收多少？净利多少？毛利率？ROE？增长率？分红？"),
    ("Q定义解释", "贵州茅台2024年的利润分配方案是怎样的？"),
    ("Q风险分析", "贵州茅台面临的主要经营风险有哪些？"),
]

times = []
for label, query in TEST_QUERIES:
    t0 = time.time()
    processed = process_query(query)
    results = hybrid_search(processed, top_k=5)
    elapsed = time.time() - t0
    times.append(elapsed)
    print(f"{elapsed:.3f}s  | chunks={len(results):3d}  | {label}: {query[:40]}")

avg = sum(times) / len(times)
print(f"\n{'='*60}")
print(f"采样 {len(times)} 题")
print(f"平均检索耗时: {avg:.3f}s ({avg*1000:.0f}ms)")
print(f"最慢: {max(times):.3f}s  最快: {min(times):.3f}s")
print(f"中位数: {sorted(times)[len(times)//2]:.3f}s")
print(f"{'✅ 平均检索 ≤3s' if avg <= 3 else '⚠️ 平均检索 >3s'}")
print(f"注：不含LLM生成时间（+3~8s），全链路预计 {avg+5:.0f}~{avg+8:.0f}s")
