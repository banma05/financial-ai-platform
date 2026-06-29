"""
RAG 检索管道 — 完整流程：混合检索 → Prompt → LLM → 返回
"""
import time
from typing import List
from loguru import logger

from config import RETRIEVAL_TOP_K
from .hybrid_search import hybrid_search
from .model_router import chat as routed_chat


def build_prompt(query: str, sources: List[dict]) -> str:
    """
    构建 RAG 提示词 - 把检索到的文档 + 用户问题拼成 prompt
    """
    context_parts = []
    for i, s in enumerate(sources, start=1):
        context_parts.append(
            f"[参考文档 {i}]（来源：{s['source']}，第 {s['page']} 页）\n{s['content']}"
        )
    context = "\n\n".join(context_parts)

    prompt = f"""你是一个专业的财务分析助手。请基于以下参考文档回答用户的问题。

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
    return prompt


def rag_query(
    query: str,
    top_k: int = RETRIEVAL_TOP_K,
) -> dict:
    """
    执行一次完整的 RAG 查询

    流程：检索 → 构建 prompt → 调用 LLM → 返回结果

    参数:
        query: 用户问题
        top_k: 检索文档数

    返回:
        {"answer": "...", "sources": [...], "processing_time": 0.5}
    """
    start_time = time.time()

    # 第一步：混合检索（BM25 + 语义 + RRF 融合 + Reranker 精排）
    sources = hybrid_search(query, top_k=top_k)
    logger.info(f"混合检索完成，返回 {len(sources)} 个文档块")

    if not sources:
        return {
            "answer": "知识库中没有找到与您问题相关的文档。请先上传相关文件后再提问。",
            "sources": [],
            "processing_time": round(time.time() - start_time, 2),
        }

    # 第二步：构建提示词
    prompt = build_prompt(query, sources)

    # 第三步：模型路由 — 自动判断任务复杂度，选择合适的模型
    messages = [
        {"role": "system", "content": "你是一个专业的财务分析助手，擅长解读财务报表、年报、审计报告等金融文档。"},
        {"role": "user", "content": prompt},
    ]
    answer = routed_chat(messages, query=query)
    processing_time = round(time.time() - start_time, 2)

    logger.info(f"RAG 查询完成，耗时 {processing_time}s")

    return {
        "answer": answer,
        "sources": [
            {
                "content": s["content"][:200] + "..." if len(s["content"]) > 200 else s["content"],
                "source": s["source"],
                "page": s["page"],
                "score": s["score"],
            }
            for s in sources
        ],
        "processing_time": processing_time,
    }
