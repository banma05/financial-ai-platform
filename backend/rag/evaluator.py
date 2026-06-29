"""
RAG 评测 — LLM-as-Judge 双标拆解

两个核心指标：
1. 上下文召回率（Context Recall）：答案信息是否在检索的文档块中
2. 忠实度（Faithfulness）：回答是否基于文档，有没有瞎编

使用指南：
- 召回率低 → 问题在切分/检索 → 优化 pipeline
- 忠实度低 → 问题在生成/Prompt → 加强校验
"""
from typing import List, Optional
from loguru import logger


def llm_judge(prompt: str) -> str:
    """用 LLM 做评判（复用已有路由）"""
    from .model_router import chat as llm_chat, TaskType
    return llm_chat(
        messages=[{"role": "user", "content": prompt}],
        task_type=TaskType.SIMPLE,
    )


def evaluate_context_recall(
    query: str,
    answer: str,
    retrieved_chunks: List[dict],
) -> dict:
    """
    上下文召回率：答案所需信息是否在检索文档中

    用 LLM 判断：把检索到的文档拼在一起，问 LLM "这个答案能不能从这些文档推断出来"
    """
    if not retrieved_chunks:
        return {"recall": 0.0, "reason": "无检索结果"}

    context = "\n---\n".join([c["content"][:500] for c in retrieved_chunks[:5]])

    prompt = f"""你是一个 RAG 系统评测专家。请判断：以下"AI生成的答案"是否能在"检索到的文档片段"中找到支撑。

评分标准（0-100）：
- 90-100：答案中的所有关键数据/事实都能在文档中找到
- 70-89：大部分能找到，少数细节文档未覆盖
- 50-69：约一半能找到
- 30-49：少部分能找到
- 0-29：基本找不到，答案在瞎编

## 用户问题
{query}

## AI生成的答案
{answer[:800]}

## 检索到的文档片段
{context[:2000]}

请只输出一个数字（0-100）和一句话原因。格式：85|原因"""

    try:
        result = llm_judge(prompt)
        parts = result.strip().split("|", 1)
        score = int(parts[0].strip()) / 100
        reason = parts[1].strip() if len(parts) > 1 else ""
    except Exception as e:
        logger.warning(f"LLM 评测召回率失败: {e}")
        score, reason = 0.5, f"评测异常: {e}"

    logger.info(f"上下文召回率(LLM-Judge): {score:.1%}")
    return {"recall": round(score, 4), "reason": reason}


def evaluate_faithfulness(
    answer: str,
    retrieved_chunks: List[dict],
) -> dict:
    """
    忠实度：回答是否基于文档，有没有瞎编

    用 LLM 逐句检查答案中的声明能否在文档中找到支撑
    """
    if not retrieved_chunks or not answer.strip():
        return {"faithfulness": 1.0, "reason": "无内容可评"}

    context = "\n---\n".join([c["content"][:500] for c in retrieved_chunks[:5]])

    prompt = f"""你是一个 RAG 系统评测专家。请判断以下 AI 生成的回答是否严格基于检索到的文档，有没有编造文档中没有的信息。

评分标准（0-100）：
- 90-100：完全基于文档，没有任何编造
- 70-89：大部分基于文档，有些合理推断
- 50-69：有较多文档未提及的内容
- 0-49：大量编造/幻觉

## 检索到的文档片段
{context[:2000]}

## AI生成的回答
{answer[:800]}

请只输出一个数字（0-100）和一句话原因。格式：85|原因"""

    try:
        result = llm_judge(prompt)
        parts = result.strip().split("|", 1)
        score = int(parts[0].strip()) / 100
        reason = parts[1].strip() if len(parts) > 1 else ""
    except Exception as e:
        logger.warning(f"LLM 评测忠实度失败: {e}")
        score, reason = 0.5, f"评测异常: {e}"

    logger.info(f"忠实度(LLM-Judge): {score:.1%}")
    return {"faithfulness": round(score, 4), "reason": reason}


def full_evaluation(
    query: str,
    answer: str,
    retrieved_chunks: List[dict],
    reference_facts: Optional[List[str]] = None,
) -> dict:
    """
    完整评测：上下文召回率 + 忠实度

    双标拆分明：
    - 召回率低 → 优化切分策略或检索算法
    - 忠实度低 → 优化 Prompt 模板或加校验
    """
    results = {
        "context_recall": evaluate_context_recall(query, answer, retrieved_chunks),
        "faithfulness": evaluate_faithfulness(answer, retrieved_chunks),
    }

    recall = results["context_recall"]["recall"]
    faith = results["faithfulness"]["faithfulness"]

    if recall < 0.7:
        results["suggestion"] = "召回率偏低 → 优先优化切分策略和检索算法"
    elif faith < 0.8:
        results["suggestion"] = "忠实度偏低 → 优化 Prompt 模板，加强'严格基于文档'约束"
    else:
        results["suggestion"] = "RAG 质量良好"

    logger.info(f"评测: 召回率={recall:.1%} 忠实度={faith:.1%} → {results['suggestion']}")
    return results
