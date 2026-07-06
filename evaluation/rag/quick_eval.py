"""
快速评测脚本 — 50 题全量评测，双轨制（关键词 + 语义），本地运行避免 HTTP 超时
"""
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # 防止 tokenizers 多线程与 CUDA 冲突导致 segfault

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from loguru import logger
from rag.hybrid_search import hybrid_search
from rag.evaluator import recall_at_k, mrr, ndcg_at_k, semantic_recall_at_k
from rag.query_processor import process_query
import json

TEST_SET = Path(__file__).parent.parent / "data" / "rag_questions.json"
TOP_K = 5

with open(TEST_SET, "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data["questions"]
logger.info(f"开始评测: {len(questions)} 题, top_k={TOP_K}")

# 关键词评测累计
total_r1, total_r3, total_r5 = 0.0, 0.0, 0.0
total_mrr, total_ndcg = 0.0, 0.0
# 语义评测累计
total_sem_r5, total_sem_sim = 0.0, 0.0
total_time = 0.0
failed_kw = []   # 关键词 R@5=0
failed_sem = []  # 语义 R@5=0
by_category = {}
by_difficulty = {}

start_all = time.time()

per_question = []  # 每题评测结果缓存，供分歧分析使用

for i, q in enumerate(questions, 1):
    qid = q["id"]
    cat = q.get("category", "unknown")
    diff = q.get("difficulty", "unknown")
    query = q["query"]
    expected = q.get("expected_keywords", [])

    q_start = time.time()
    try:
        processed = process_query(query)
        chunks = hybrid_search(processed, top_k=TOP_K)
    except Exception as e:
        logger.error(f"{qid} 检索失败: {e}")
        failed_kw.append(qid)
        continue
    q_time = time.time() - q_start
    total_time += q_time

    # 关键词指标
    r1 = recall_at_k(query, expected, chunks, k=1)["recall@k"]
    r3 = recall_at_k(query, expected, chunks, k=3)["recall@k"]
    r5 = recall_at_k(query, expected, chunks, k=5)["recall@k"]
    mr = mrr(expected, chunks)["mrr"]
    nd = ndcg_at_k(expected, chunks, k=5)["ndcg@k"]

    # 语义指标
    sem = semantic_recall_at_k(query, chunks, k=TOP_K)
    sem_r5 = sem["semantic_recall@k"]
    sem_sim = sem["avg_similarity"]

    total_r1 += r1
    total_r3 += r3
    total_r5 += r5
    total_mrr += mr
    total_ndcg += nd
    total_sem_r5 += sem_r5
    total_sem_sim += sem_sim

    # 按类别/难度分组
    for group, key in [(by_category, cat), (by_difficulty, diff)]:
        if key not in group:
            group[key] = {"count": 0, "kw_r5": 0.0, "sem_r5": 0.0, "mrr": 0.0}
        group[key]["count"] += 1
        group[key]["kw_r5"] += r5
        group[key]["sem_r5"] += sem_r5
        group[key]["mrr"] += mr

    # 关键词 vs 语义差异标记
    if r5 >= 0.8 and sem_r5 >= 0.6:
        status = "[OK]"
    elif r5 < 0.4 and sem_r5 >= 0.6:
        status = "[KW?]"  # 关键词低但语义高 → 关键词标注可能不全
    elif r5 >= 0.6 and sem_r5 < 0.4:
        status = "[SEM?]"  # 关键词高但语义低 → 关键词太宽泛
    elif r5 >= 0.4:
        status = "[WARN]"
    else:
        status = "[FAIL]"

    logger.info(f"{status} {qid} [{cat}][{diff}] KW-R@5={r5:.1%} SEM-R@5={sem_r5:.1%} MRR={mr:.1%} | {q_time:.1f}s | {query[:40]}...")

    if r5 == 0.0:
        failed_kw.append(qid)
    if sem_r5 == 0.0:
        failed_sem.append(qid)

    # 保存每题结果供分歧分析
    per_question.append({
        "qid": qid, "query": query[:60], "cat": cat, "diff": diff,
        "kw_r5": r5, "sem_r5": sem_r5, "mrr": mr, "status": status,
    })

elapsed = time.time() - start_all
n = len(questions)

# ============ 报告 ============
print("\n" + "=" * 70)
print(">>> 50 题全量评测报告（双轨制：关键词 + 语义）<<<")
print("=" * 70)
print(f"题目数: {n}")
print(f"关键词失败题 (KW-R@5=0): {len(failed_kw)} — {failed_kw if failed_kw else '无'}")
print(f"语义失败题   (SEM-R@5=0): {len(failed_sem)} — {failed_sem if failed_sem else '无'}")
print(f"总耗时: {elapsed:.1f}s | 平均单题: {total_time/n:.1f}s")
print()

print(f"| 指标 | 关键词 | 语义 |")
print(f"|------|:--:|:--:|")
print(f"| Recall@1 | {total_r1/n*100:.1f}% | - |")
print(f"| Recall@3 | {total_r3/n*100:.1f}% | - |")
print(f"| **Recall@5** | **{total_r5/n*100:.1f}%** | **{total_sem_r5/n*100:.1f}%** |")
print(f"| MRR       | {total_mrr/n*100:.1f}% | - |")
print(f"| NDCG@5    | {total_ndcg/n*100:.1f}% | - |")
print(f"| Avg Sim   | - | {total_sem_sim/n:.3f} |")
print()

# 差异分析：找出关键词和语义分歧的题
print(f"### 关键词-语义分歧分析（标注质量信号）")
diverged_kw = [q for q in per_question if q["status"] == "[KW?]"]
diverged_sem = [q for q in per_question if q["status"] == "[SEM?]"]

print(f"| 含义 |")
print(f"|------|")
print(f"| [KW?] 关键词低+语义高 → expected_keywords 标注不全，检索实际 OK |")
print(f"| [SEM?] 关键词高+语义低 → 关键词太宽泛或无区分度 |")
print()

if diverged_kw:
    print(f"**关键词标注不全 ({len(diverged_kw)} 题)：**")
    print(f"| 题号 | 类别 | KW-R@5 | SEM-R@5 | 问题 |")
    print(f"|------|------|:--:|:--:|------|")
    for q in diverged_kw:
        print(f"| {q['qid']} | {q['cat']} | {q['kw_r5']:.0%} | {q['sem_r5']:.0%} | {q['query']} |")
    print()

if diverged_sem:
    print(f"**关键词过于宽泛 ({len(diverged_sem)} 题)：**")
    print(f"| 题号 | 类别 | KW-R@5 | SEM-R@5 | 问题 |")
    print(f"|------|------|:--:|:--:|------|")
    for q in diverged_sem:
        print(f"| {q['qid']} | {q['cat']} | {q['kw_r5']:.0%} | {q['sem_r5']:.0%} | {q['query']} |")
    print()

if not diverged_kw and not diverged_sem:
    print("无显著分歧题。✅")
print()

print(f"### 按难度")
print(f"| 难度 | 题数 | KW-R@5 | SEM-R@5 | MRR |")
print(f"|------|:--:|:--:|:--:|:--:|")
for d in ["easy", "medium", "hard"]:
    g = by_difficulty.get(d, {"count": 0, "kw_r5": 0, "sem_r5": 0, "mrr": 0})
    if g["count"] > 0:
        print(f"| {d} | {g['count']} | {g['kw_r5']/g['count']*100:.1f}% | {g['sem_r5']/g['count']*100:.1f}% | {g['mrr']/g['count']*100:.1f}% |")

print(f"\n### 按类别")
print(f"| 类别 | 题数 | KW-R@5 | SEM-R@5 | MRR |")
print(f"|------|:--:|:--:|:--:|:--:|")
for cat in sorted(by_category.keys()):
    g = by_category[cat]
    print(f"| {cat} | {g['count']} | {g['kw_r5']/g['count']*100:.1f}% | {g['sem_r5']/g['count']*100:.1f}% | {g['mrr']/g['count']*100:.1f}% |")

# 与旧基线对比
print(f"\n### 与旧基线对比")
print(f"| 指标 | 旧基线(33题,mean-0.5std) | 新基线(50题,mean-1std) | 变化 |")
print(f"|------|:--:|:--:|:--:|")
old_r5, old_mrr = 87.3, 90.8
new_r5 = total_r5 / n * 100
new_mrr = total_mrr / n * 100
delta_r5 = new_r5 - old_r5
delta_mrr = new_mrr - old_mrr
print(f"| KW-Recall@5 | {old_r5}% | {new_r5:.1f}% | {delta_r5:+.1f}pp |")
print(f"| MRR | {old_mrr}% | {new_mrr:.1f}% | {delta_mrr:+.1f}pp |")
print(f"| SEM-Recall@5 | - | {total_sem_r5/n*100:.1f}% | 新增指标 |")

print(f"\n评测完成 [OK]")
