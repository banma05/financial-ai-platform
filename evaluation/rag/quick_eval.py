"""
RAG 评测脚本 — RAGAS 三指标 + answerable 分类

检索指标（确定性，零成本）：
  SEM-R@5 — query-chunk 余弦相似度 ≥0.5 的比例

生成指标（pro judge，稳定可复现）：
  Faithfulness      — 答案是否严格基于检索文档（对标 RAGAS Faithfulness）
  Answer Relevancy  — 答案是否切实回应了用户问题（对标 RAGAS Answer Relevancy）
  Context Recall    — 答案关键信息能否在检索文档中找到（对标 RAGAS Context Recall）

answerable 分类：
  answerable=true  → 三指标全测
  answerable=false → 测 Honesty（关键词匹配，确定性）

设计原则：
  - Judge 用 deepseek-v4-pro（flash 评分不可复现）
  - Context Precision 已砍——SEM-R@5=96% 已证明检索质量
  - 对标 RAGAS 金标准三指标
"""
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"

_LIGHT_MODE = os.environ.get("EVAL_LIGHT", "").lower() in ("1", "true", "yes")
if _LIGHT_MODE:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

import sys
import time
import argparse
import json
from pathlib import Path

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from loguru import logger
from rag.hybrid_search import hybrid_search
from rag.evaluator import (
    semantic_recall_at_k,
    evaluate_faithfulness,
    evaluate_context_recall,
    evaluate_answer_relevancy,
    is_answer_honest,
)
from rag.query_processor import process_query
from rag.retriever import build_prompt, build_honesty_prompt
from rag.model_router import chat as llm_chat, TaskType

TEST_SET = Path(__file__).parent.parent / "data" / "rag_questions.json"
BOUNDARY_SET = Path(__file__).parent.parent / "data" / "rag_questions_boundary.json"
TOP_K = 5

parser = argparse.ArgumentParser(description="RAG 三指标评测（RAGAS 标准）")
parser.add_argument("--include-boundary", action="store_true")
parser.add_argument("--skip-generation", action="store_true",
                    help="仅检索评测，零成本")
args = parser.parse_args()

with open(TEST_SET, "r", encoding="utf-8") as f:
    data = json.load(f)

questions = data["questions"]

if args.include_boundary and BOUNDARY_SET.exists():
    with open(BOUNDARY_SET, "r", encoding="utf-8") as f:
        questions = questions + json.load(f)["questions"]

LIGHT_MODE = _LIGHT_MODE
SKIP_GEN = args.skip_generation or LIGHT_MODE
mode_desc = "轻量（仅检索）" if SKIP_GEN else "全量（RAGAS 三指标，pro judge）"
logger.info(f"开始: {len(questions)} 题, top_k={TOP_K}, 模式={mode_desc}")

# ============ 累计变量 ============
total_sem_r5 = 0.0
total_sem_sim = 0.0
total_faithfulness = 0.0
total_context_recall = 0.0
total_answer_relevancy = 0.0
total_retrieval_time = 0.0
total_gen_time = 0.0
ans_count = 0
total_honest = 0
unans_count = 0

failed_sem = []
per_question = []

start_all = time.time()

for i, q in enumerate(questions, 1):
    qid = q["id"]
    cat = q.get("category", "unknown")
    diff = q.get("difficulty", "unknown")
    query = q["query"]
    answerable = q.get("answerable", True)

    # ── 检索 ──
    q_start = time.time()
    try:
        processed = process_query(query)
        chunks = hybrid_search(processed, top_k=TOP_K, force_rerank=not LIGHT_MODE)
    except Exception as e:
        logger.error(f"{qid} 检索失败: {e}")
        failed_sem.append(qid)
        continue
    retrieval_time = time.time() - q_start
    total_retrieval_time += retrieval_time

    if LIGHT_MODE:
        sem_r5, sem_sim = 0.0, 0.0
    else:
        sem = semantic_recall_at_k(query, chunks, k=TOP_K)
        sem_r5 = sem["semantic_recall@k"]
        sem_sim = sem["avg_similarity"]
        total_sem_r5 += sem_r5
        total_sem_sim += sem_sim

    # ── 生成 + Judge ──
    faithfulness = None
    context_recall = None
    answer_relevancy = None
    is_honest = None
    gen_time = 0.0

    if not SKIP_GEN and chunks:
        gen_start = time.time()
        try:
            if answerable:
                prompt = build_prompt(query, chunks[:5])
            else:
                prompt = build_honesty_prompt(query, chunks[:5])

            answer = llm_chat(
                messages=[{"role": "user", "content": prompt}],
                task_type=TaskType.SIMPLE,  # 生成仍用 flash（反映生产环境）
            )

            if answerable:
                faith_result = evaluate_faithfulness(answer, chunks)
                recall_result = evaluate_context_recall(query, answer, chunks)
                relevancy_result = evaluate_answer_relevancy(query, answer, chunks)

                faithfulness = faith_result["faithfulness"]
                context_recall = recall_result["recall"]
                answer_relevancy = relevancy_result["answer_relevancy"]

                total_faithfulness += faithfulness
                total_context_recall += context_recall
                total_answer_relevancy += answer_relevancy
                ans_count += 1
            else:
                honest_result = is_answer_honest(answer)
                is_honest = honest_result["is_honest"]
                if is_honest:
                    total_honest += 1
                unans_count += 1

            gen_time = time.time() - gen_start
            total_gen_time += gen_time
        except Exception as e:
            logger.warning(f"{qid} 生成/评测失败: {e}")

    # ── 日志 ──
    if sem_r5 >= 0.6:
        status = "[OK]"
    elif sem_r5 >= 0.4:
        status = "[WARN]"
    else:
        status = "[FAIL]"

    if answerable:
        f_str = f"Faith={faithfulness:.0%}" if faithfulness is not None else "N/A"
        c_str = f"CRec={context_recall:.0%}" if context_recall is not None else "N/A"
        a_str = f"ARel={answer_relevancy:.0%}" if answer_relevancy is not None else "N/A"
        logger.info(f"{status} {qid} [{cat}][{diff}] SEM={sem_r5:.0%} | {f_str} {c_str} {a_str} | "
                    f"检索{retrieval_time:.1f}s" + (f" 生成{gen_time:.1f}s" if gen_time > 0 else "")
                    + f" | {query[:40]}...")
    else:
        h_str = "诚实" if is_honest else "未诚实"
        logger.info(f"{status} {qid} [{cat}][{diff}][不可答] SEM={sem_r5:.0%} | {h_str} | "
                    f"检索{retrieval_time:.1f}s" + (f" 生成{gen_time:.1f}s" if gen_time > 0 else "")
                    + f" | {query[:40]}...")

    per_question.append({
        "qid": qid, "query": query[:60], "cat": cat, "diff": diff,
        "answerable": answerable,
        "sem_r5": sem_r5, "sem_sim": sem_sim,
        "faithfulness": faithfulness, "context_recall": context_recall,
        "answer_relevancy": answer_relevancy,
        "is_honest": is_honest,
        "status": status,
    })

elapsed = time.time() - start_all
n = len(questions)
n_ans = sum(1 for q in questions if q.get("answerable", True))
n_unans = n - n_ans

# ============ 报告 ============
print("\n" + "=" * 70)
print(">>> RAG 评测报告（RAGAS 三指标）<<<")
print("=" * 70)
print(f"题目: {n} (可回答 {n_ans}, 不可回答 {n_unans}) | Judge: pro | 耗时: {elapsed:.1f}s")
if LIGHT_MODE:
    print("⚡ 轻量模式")
print()

# ── 检索 ──
print("─" * 70)
print("【检索】SEM-R@5（Embedding 余弦相似度，确定性）")
print("─" * 70)
print(f"  SEM-R@5         {total_sem_r5/n*100:5.1f}%   (top-5 语义相关比例)")
print(f"  平均相似度       {total_sem_sim/n:.3f}     (query-chunk 余弦相似度均值)")
print(f"  平均检索耗时     {total_retrieval_time/n:.1f}s")
if failed_sem:
    print(f"  ⚠️ 检索失败: {failed_sem}")
print()

# ── 生成 ──
if SKIP_GEN:
    print("【生成】已跳过")
elif ans_count == 0:
    print("【生成】评测失败 — 检查 API")
else:
    print("─" * 70)
    print(f"【生成】可回答题 ({ans_count} 题) — RAGAS 三指标（pro judge）")
    print("─" * 70)
    print(f"  指标               值        对标 RAGAS      达标?")
    print(f"  ────────────────  ────────  ──────────────  ────")
    avg_faith = total_faithfulness/ans_count
    avg_crec = total_context_recall/ans_count
    avg_arel = total_answer_relevancy/ans_count
    print(f"  Faithfulness      {avg_faith*100:5.1f}%       ≥ 90%           {'✅' if avg_faith >= 0.9 else '❌'}")
    print(f"  Answer Relevancy  {avg_arel*100:5.1f}%       ≥ 85%           {'✅' if avg_arel >= 0.85 else '❌'}")
    print(f"  Context Recall    {avg_crec*100:5.1f}%       ≥ 85%           {'✅' if avg_crec >= 0.85 else '❌'}")

    if unans_count > 0:
        print(f"\n  不可回答题 ({unans_count} 题): 不参与 Faithfulness/ARel/CRec 评分")
        unhonest = [q for q in per_question
                    if not q.get("answerable", True) and q.get("is_honest") is not None and not q["is_honest"]]
        if unhonest:
            print(f"  文档缺失题: {[q['qid'] for q in unhonest]}")

    print(f"\n  评测耗时 {total_gen_time:.1f}s | 约 ¥0.40-0.60")

# ── 逐题 ──
print(f"\n── 逐题详情 ──")
print(f"  题号    可答  SEM     Faith   CRec    ARel    Honest")
print(f"  ──────  ────  ──────  ──────  ──────  ──────  ──────")
for q in per_question:
    ab = "是" if q.get("answerable", True) else "否"
    sem = f"{q['sem_r5']:.0%}" if q.get('sem_r5') is not None else "N/A"
    f = f"{q['faithfulness']:.0%}" if q.get('faithfulness') is not None else "N/A"
    c = f"{q['context_recall']:.0%}" if q.get('context_recall') is not None else "N/A"
    a = f"{q['answer_relevancy']:.0%}" if q.get('answer_relevancy') is not None else "N/A"
    h = "✓" if q.get('is_honest') else ("✗" if q.get('is_honest') is False else "N/A")
    print(f"  {q['qid']:6s}  {ab:4s}  {sem:6s}  {f:6s}  {c:6s}  {a:6s}  {h:6s}")

# ── 低分 ──
low_sem = [q for q in per_question if q.get("sem_r5", 0) < 0.6]
if low_sem:
    print(f"\n── ⚠️ 检索低分 (SEM < 60%) ──")
    for q in low_sem:
        print(f"  {q['qid']} [{q['cat']}] SEM={q['sem_r5']:.0%} | {q['query']}")

if ans_count > 0:
    low_faith = [q for q in per_question
                 if q.get("faithfulness") is not None and q["faithfulness"] < 0.7]
    if low_faith:
        print(f"\n── ⚠️ 忠实性低分 (Faith < 70%) ──")
        for q in low_faith:
            print(f"  {q['qid']} [{q['cat']}] Faith={q['faithfulness']:.0%} | {q['query']}")

# ── 基线 ──
print(f"\n── V8.3 RAG 评测基线（对标 RAGAS）──")
print(f"  指标               值        目标      方法")
print(f"  ────────────────  ────────  ────────  ──────────────")
print(f"  SEM-R@5           {total_sem_r5/n*100:.1f}%       ≥ 90%     Embedding（确定性）")
if ans_count > 0:
    print(f"  Faithfulness      {total_faithfulness/ans_count*100:.1f}%       ≥ 90%     pro judge")
    print(f"  Answer Relevancy  {total_answer_relevancy/ans_count*100:.1f}%       ≥ 85%     pro judge")
    print(f"  Context Recall    {total_context_recall/ans_count*100:.1f}%       ≥ 85%     pro judge")

print(f"\n评测完成 ✓\n")
