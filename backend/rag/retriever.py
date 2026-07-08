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


def build_prompt(query: str, sources: List[dict], history: Optional[List[dict]] = None) -> str:
    context_parts = []
    for i, s in enumerate(sources, start=1):
        # 结构化引用格式：[^1] 来源 | 文件名 | 页码 | 相似度
        score_pct = f"{s.get('score', 0) * 100:.0f}%" if s.get('score') else "N/A"
        context_parts.append(
            f"[^{i}] **{s['source']}** (第{s['page']}页, 相似度{score_pct})\n{s['content']}"
        )
    context = "\n\n".join(context_parts)

    # 历史对话（最近 3 轮，控制 token 消耗）
    history_text = ""
    if history:
        recent = history[-6:]  # 最近 3 轮 = 6 条消息
        lines = []
        for msg in recent:
            role_label = "用户" if msg["role"] == "user" else "助手"
            lines.append(f"{role_label}：{msg['content']}")
        if lines:
            history_text = "## 历史对话\n" + "\n".join(lines) + "\n\n"

    return f"""你是一个专业的财务分析助手。请基于以下参考文档回答用户的问题。

要求：
1. 严格基于参考文档的内容回答，不要编造信息
2. 如果参考文档中没有相关信息，请明确说"文档中未找到相关信息"
3. 结合历史对话上下文理解用户问题（如"它"指代的对象、追问的隐含前提）
4. 回答要专业、准确，适合金融专业人士阅读
5. 文中引用数据时使用 [^N] 脚注标记（N 为参考文档编号）
6. 回答末尾用 `---` 分隔后列出引用清单，格式为 `[^N]: 文件名, 第X页`

{history_text}## 参考文档
{context}

## 用户问题
{query}

## 回答"""


def rag_query(
    query: str,
    top_k: int = RETRIEVAL_TOP_K,
    eval_facts: Optional[List[str]] = None,
    history: Optional[List[dict]] = None,
) -> dict:
    """
    四步口诀完整 RAG 流程

    流程：Query 处理 → 混合检索 → 构建 prompt → LLM → 评测
    """
    start_time = time.time()
    original_query = query

    # 第二步：Query 处理（术语展开 → 多轮改写 → 扩写 → 校验）
    processed_query = process_query(query, history=history)
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

    # 构建 Prompt + LLM 生成（含历史对话）
    prompt = build_prompt(processed_query, sources, history=history)
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


def save_chat_turn(
    session_id: str,
    role: str,
    content: str,
    query: str = "",
    processing_time: float = 0.0,
    sources: list = None,
):
    """
    将对话轮次持久化到 chat_history 表（V6.0 新增）。

    与 api/rag.py 中的内存缓存并行写入，实现"读从内存、写落DB"双写模式。
    写入失败不影响主流程（静默降级）。
    """
    from db import SessionLocal, ChatHistory
    db = SessionLocal()
    try:
        record = ChatHistory(
            session_id=session_id,
            role=role,
            query=query if role == "assistant" else content,
            answer=content if role == "assistant" else "",
            sources_json=sources or [],
            processing_time=processing_time,
        )
        db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"ChatHistory 写入失败（静默降级）: {e}")
    finally:
        db.close()
