"""
快速评测脚本 — 50 题全量评测，双轨制（关键词 + 语义），本地运行避免 HTTP 超时
"""
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # 防止 tokenizers 多线程与 CUDA 冲突导致 segfault

# ── 轻量模式：必须在所有 import 之前禁用 CUDA ──
_LIGHT_MODE = os.environ.get("EVAL_LIGHT", "").lower() in ("1", "true", "yes")
if _LIGHT_MODE:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""  # PyTorch 初始化前禁用 GPU

import sys
import time
import argparse
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
# 复用模块顶部已读取的轻量模式标记
LIGHT_MODE = _LIGHT_MODE

logger.info(f"开始评测: {len(questions)} 题, top_k={TOP_K}, light={LIGHT_MODE}")

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
        chunks = hybrid_search(processed, top_k=TOP_K, force_rerank=not LIGHT_MODE)
    except Exception as e:
        logger.error(f"{qid} 检索失败: {e}")
        failed_kw.append(qid)
        continue
    q_time = time.time() - q_start
    total_time += q_time

    # ── V8.2: 关键词评测仅在有关键词标注时运行 ──
    has_keywords = bool(expected)
    if has_keywords:
        r1 = recall_at_k(query, expected, chunks, k=1)["recall@k"]
        r3 = recall_at_k(query, expected, chunks, k=3)["recall@k"]
        r5 = recall_at_k(query, expected, chunks, k=5)["recall@k"]
        mr = mrr(expected, chunks)["mrr"]
        nd = ndcg_at_k(expected, chunks, k=5)["ndcg@k"]
        total_r1 += r1; total_r3 += r3; total_r5 += r5
        total_mrr += mr; total_ndcg += nd
    else:
        r1 = r3 = r5 = mr = nd = None  # N/A：无关键词标注

    # 语义指标（轻量模式下跳过）
    if LIGHT_MODE:
        sem_r5, sem_sim = 0.0, 0.0
    else:
        sem = semantic_recall_at_k(query, chunks, k=TOP_K)
        sem_r5 = sem["semantic_recall@k"]
        sem_sim = sem["avg_similarity"]
        total_sem_r5 += sem_r5
        total_sem_sim += sem_sim

    # 按类别/难度分组
    for group, key in [(by_category, cat), (by_difficulty, diff)]:
        if key not in group:
            group[key] = {"count": 0, "kw_r5": 0.0, "kw_count": 0, "sem_r5": 0.0, "mrr": 0.0}
        group[key]["count"] += 1
        if has_keywords:
            group[key]["kw_r5"] += r5
            group[key]["kw_count"] += 1
            group[key]["mrr"] += mr
        group[key]["sem_r5"] += sem_r5

    # 状态标记
    if not has_keywords:
        status = "[N/A]"  # 无关键词标注，以语义评测为准
    elif r5 >= 0.8 and sem_r5 >= 0.6:
        status = "[OK]"
    elif r5 < 0.4 and sem_r5 >= 0.6:
        status = "[KW?]"  # 关键词低但语义高 → 关键词标注可能不全
    elif r5 >= 0.6 and sem_r5 < 0.4:
        status = "[SEM?]"  # 关键词高但语义低 → 关键词太宽泛
    elif r5 >= 0.4:
        status = "[WARN]"
    else:
        status = "[FAIL]"

    kw_str = f"KW-R@5={r5:.1%}" if has_keywords else "KW-R@5=N/A"
    logger.info(f"{status} {qid} [{cat}][{diff}] {kw_str} SEM-R@5={sem_r5:.1%} | {q_time:.1f}s | {query[:40]}...")

    if has_keywords and r5 == 0.0:
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
# V8.2: 检测关键词标注覆盖率
kw_labeled = sum(1 for q in questions if q.get("expected_keywords"))
kw_unlabeled = n - kw_labeled

print("\n" + "=" * 70)
print(">>> 50 题全量评测报告（双轨制：关键词 + 语义）<<<")
print("=" * 70)
print(f"题目数: {n} | 有标注: {kw_labeled} | 无标注: {kw_unlabeled} | 总耗时: {elapsed:.1f}s")
if LIGHT_MODE:
    print("⚡ 轻量模式：已跳过 CrossEncoder 重排 + 语义评测")
if kw_unlabeled > 0:
    print(f"⚠️ {kw_unlabeled} 题缺少 expected_keywords 标注 → 关键词评测仅覆盖 {kw_labeled} 题")
if failed_kw:
    print(f"关键词失败题: {len(failed_kw)} — {failed_kw}")
if not LIGHT_MODE and failed_sem:
    print(f"语义失败题: {len(failed_sem)} — {failed_sem}")
print()

# 指标汇总（关键词仅统计有标注的题）
kw_n = kw_labeled if kw_labeled > 0 else 1  # 避免除零
print(f"| 指标 | 关键词 ({kw_labeled}题) | 语义 (50题) |")
print(f"|------|:--:|:--:|")
if kw_labeled > 0:
    print(f"| Recall@1 | {total_r1/kw_n*100:.1f}% | - |")
    print(f"| Recall@3 | {total_r3/kw_n*100:.1f}% | - |")
    print(f"| **Recall@5** | **{total_r5/kw_n*100:.1f}%** | **{total_sem_r5/n*100:.1f}%** |")
    print(f"| MRR       | {total_mrr/kw_n*100:.1f}% | - |")
    print(f"| NDCG@5    | {total_ndcg/kw_n*100:.1f}% | - |")
else:
    print(f"| Recall@5 | N/A (无标注) | **{total_sem_r5/n*100:.1f}%** |")
    print(f"| MRR | N/A (无标注) | - |")
    print(f"| **语义是当前唯一的检索质量指标** |||")
print(f"| Avg Sim   | - | {total_sem_sim/n:.3f} |")
print()

# 差异分析
na_questions = [q for q in per_question if q["status"] == "[N/A]"]
if na_questions:
    print(f"### ⚠️ 关键词标注缺失 ({len(na_questions)} 题)")
    print(f"以语义评测为准。如需关键词评分，请在 rag_questions.json 中补充 expected_keywords。")
    print()

diverged_kw = [q for q in per_question if q["status"] == "[KW?]"]
if diverged_kw:
    print(f"**关键词标注不全 ({len(diverged_kw)} 题)：")
    for q in diverged_kw:
        print(f"  {q['qid']} [{q['cat']}] KW={q['kw_r5']:.0%} SEM={q['sem_r5']:.0%} | {q['query']}")

print(f"\n### 按难度")
print(f"| 难度 | 题数 | KW-R@5 | SEM-R@5 |")
print(f"|------|:--:|:--:|:--:|")
for d in ["easy", "medium", "hard"]:
    g = by_difficulty.get(d, {"count": 0, "kw_r5": 0, "kw_count": 0, "sem_r5": 0})
    if g["count"] > 0:
        kw_str = f"{g['kw_r5']/g['kw_count']*100:.1f}%" if g['kw_count'] > 0 else "N/A"
        print(f"| {d} | {g['count']} | {kw_str} | {g['sem_r5']/g['count']*100:.1f}% |")

print(f"\n### 按类别")
print(f"| 类别 | 题数 | KW-R@5 | SEM-R@5 |")
print(f"|------|:--:|:--:|:--:|")
for cat in sorted(by_category.keys()):
    g = by_category[cat]
    kw_str = f"{g['kw_r5']/g['kw_count']*100:.1f}%" if g['kw_count'] > 0 else "N/A"
    print(f"| {cat} | {g['count']} | {kw_str} | {g['sem_r5']/g['count']*100:.1f}% |")
# V8.2 评测汇总
print(f"\n### V8.2 检索评测基线")
print(f"| 指标 | 值 | 说明 |")
print(f"|------|:--:|------|")
print(f"| 语义召回 SEM-R@5 | {total_sem_r5/n*100:.1f}% | 主要指标：query-chunk 余弦相似度≥0.5 的比例 |")
print(f"| 语义平均相似度 | {total_sem_sim/n:.3f} | top-5 chunk 的平均余弦相似度 |")
if kw_labeled == 0:
    print(f"| 关键词评测 | N/A | {n} 题均无 expected_keywords 标注，以语义评测为准 |")
else:
    print(f"| 关键词 KW-R@5 | {total_r5/kw_labeled*100:.1f}% | {kw_labeled} 题有关键词标注 |")
print(f"| 平均检索耗时 | {total_time/n:.1f}s | 轻量模式{' + CrossEncoder 重排' if not LIGHT_MODE else ''} |")

print(f"\n评测完成 [OK]")
