"""
RAG 检索管道 — 四步口诀完整版

一、语义动态切分（semantic_splitter）
二、Query 处理：短句扩写 + 余弦校验（query_processor）
三、混合检索：BM25 + 语义 + LambdaMART 统一打分（hybrid_search）
四、指标拆解：上下文召回率 + 忠实度（evaluator）
"""
import time
from typing import List, Optional
from loguru import logger

from config import RETRIEVAL_TOP_K
from .query_processor import process_query
from .hybrid_search import hybrid_search
from .model_router import chat as routed_chat


def build_prompt(query: str, sources: List[dict]) -> str:
    context_parts = []
    for i, s in enumerate(sources, start=1):
        context_parts.append(
            f"[参考文档 {i}]（来源：{s['source']}，第 {s['page']} 页）\n{s['content']}"
        )
    context = "\n\n".join(context_parts)

    return f"""你是一个专业的财务分析助手。请基于以下参考文档回答用户的问题。

要求：
1. 严格基于参考文档的内容回答，不要编造信息
2. 如果参考文档中没有相关信息，请明确说"文档中未找到相关信息"
3. 回答要专业、准确，适合金融专业人士阅读
4. 在回答末尾列出你引用的文档来源和页码

## 参考文档
{context}

## 用户问题
{query}

## 回答"""


def rag_query(
    query: str,
    top_k: int = RETRIEVAL_TOP_K,
    eval_facts: Optional[List[str]] = None,
) -> dict:
    """
    四步口诀完整 RAG 流程

    流程：Query 处理 → 混合检索 → 构建 prompt → LLM → 评测
    """
    start_time = time.time()
    original_query = query

    # 第二步：Query 处理（短句扩写 + 余弦校验 <0.8 废弃）
    processed_query = process_query(query)
    if processed_query != original_query:
        logger.info(f"Query processed: '{original_query[:30]}...' -> '{processed_query[:30]}...'")

    # 第三步：混合检索（向量 + BM25 + LambdaMART 统一打分）
    sources = hybrid_search(processed_query, top_k=top_k)
    logger.info(f"Retrieved {len(sources)} chunks")

    if not sources:
        return {
            "answer": "知识库中没有找到与您问题相关的文档。请先上传相关文件后再提问。",
            "sources": [],
            "processing_time": round(time.time() - start_time, 2),
        }

    # 构建 Prompt + LLM 生成
    prompt = build_prompt(processed_query, sources)
    messages = [
        {"role": "system", "content": "你是一个专业的财务分析助手，擅长解读财务报表、年报、审计报告等金融文档。"},
        {"role": "user", "content": prompt},
    ]
    answer = routed_chat(messages, query=processed_query)
    processing_time = round(time.time() - start_time, 2)

    logger.info(f"RAG query done in {processing_time}s")

    result = {
        "answer": answer,
        "sources": [
            {
                "content": s["content"][:200] + "..." if len(s["content"]) > 200 else s["content"],
                "source": s["source"],
                "page": s["page"],
                "score": s.get("rerank_score", s.get("rrf_score", s.get("score", 0))),
            }
            for s in sources
        ],
        "processing_time": processing_time,
        "processed_query": processed_query if processed_query != original_query else None,
    }

    # 第四步：评测
    if eval_facts:
        from .evaluator import full_evaluation
        result["evaluation"] = full_evaluation(
            query=original_query,
            answer=answer,
            retrieved_chunks=sources,
            reference_facts=eval_facts,
        )

    return result
