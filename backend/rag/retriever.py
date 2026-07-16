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
        # 结构化引用格式：[1] 来源 | 文件名 | 页码
        score_pct = f"{s.get('score', 0) * 100:.0f}%" if s.get('score') else "N/A"
        context_parts.append(
            f"[{i}] **{s['source']}** (第{s['page']}页, 相似度{score_pct})\n{s['content']}"
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

## ⚠️ 核心铁律（违反任一条即为严重错误）

1. **只能使用上面参考文档中的内容**，绝对禁止编造、猜测或凭记忆补充任何信息
2. **每一个数字必须标注来源编号**，格式为 `[N]`（N 为参考文档编号）。如果没有来源支撑的数字，一个字都不能写
3. **如果参考文档中没有相关信息**，必须明确说"文档中未找到相关信息"，不得兜圈子或含糊其辞
4. **禁止四舍五入或近似表达**：文档中写 1708.99 就必须写 1708.99，不能写"约1709亿"或"1700多亿"
5. **禁止推断不在文档中的趋势**：如文档只提到2024年数据，不能说"近年来持续增长"

## 其他要求
- 结合历史对话上下文理解用户问题（如"它"指代的对象、追问的隐含前提）
- 回答要专业、准确，适合金融专业人士阅读
- 回答末尾用 `---` 分隔后列出引用清单，格式为 `[N]: 文件名, 第X页`

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
        {"role": "system", "content": (
            "你是一个严谨的财务分析助手，擅长解读财务报表、年报、审计报告等金融文档。"
            "你的回答必须严格基于提供的参考文档，绝不编造。无数据就说无数据。"
        )},
        {"role": "user", "content": prompt},
    ]
    answer = routed_chat(messages, query=processed_query)

    # ── V8.2: 后处理幻觉检测 ──
    hallucination_warning = _check_hallucination(answer, sources)
    if hallucination_warning:
        logger.warning(f"[幻觉检测] {hallucination_warning}")

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


def _check_hallucination(answer: str, sources: List[dict]) -> Optional[str]:
    """
    V8.2 后处理幻觉检测：检查回答中的数字/关键数据是否出现在来源文档中。

    使用 BM25 语义匹配：
    1. 提取回答中的所有数字（含上下文）
    2. 在来源文档中检查是否存在
    3. 返回未在文档中找到的数字片段（供日志记录）

    返回 None 表示通过检测，返回字符串表示发现潜在幻觉。
    """
    import re

    if not sources or not answer:
        return None

    # 提取回答中的数字及其上下文（前后10个字符）
    number_spans = re.finditer(r'(\d+\.?\d*)', answer)
    unchecked_numbers = []  # 跳过短数字（年份、百分比等）
    suspicious = []

    for match in number_spans:
        num = match.group(1)
        # 跳过短数字（年份如 2024、纯数字如百分数分数等）
        if len(num) <= 2:
            continue
        # 取数字前后各 15 个字符作为上下文
        start = max(0, match.start() - 15)
        end = min(len(answer), match.end() + 15)
        ctx = answer[start:end].strip()
        unchecked_numbers.append((num, ctx))

    if not unchecked_numbers:
        return None

    # 构建来源文档的全文
    source_texts = [s["content"] for s in sources]

    # 检查每个数字
    for num, ctx in unchecked_numbers:
        found = any(num in text for text in source_texts)
        if not found:
            # 再尝试浮点精度匹配（如 1708.99 vs 1709.0）
            try:
                num_f = float(num)
                for text in source_texts:
                    for src_num in re.findall(r'\d+\.?\d*', text):
                        try:
                            if abs(num_f - float(src_num)) < 0.015:
                                found = True
                                break
                        except ValueError:
                            pass
                    if found:
                        break
            except ValueError:
                pass

        if not found:
            suspicious.append(f"'{ctx}'")

    if suspicious:
        return f"发现 {len(suspicious)} 处潜在幻觉: {suspicious[:3]}"
    return None


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
