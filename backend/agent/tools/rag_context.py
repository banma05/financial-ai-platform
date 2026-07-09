"""
RAG 上下文工具 — 从知识库检索文字解读和原文引用

V8.0 新增：为 Agent 提供"查原因"能力。与 DataQueryTool（查数字）互补。
- DataQuery: SQL 查数字（毫秒，100%准确）
- RAGContext: RAG 查原因（检索原文，LLM提炼，附引用）
"""
from typing import List, Dict, Any, Optional
from loguru import logger


class RAGContextTool:
    """从知识库检索文字上下文，用于报告中的解读和溯源"""

    def __init__(self):
        self.name = "rag_context"

    def run(self, query: str, top_k: int = 5, **kwargs) -> dict:
        """
        检索知识库中的相关文字，LLM 提炼关键信息。

        参数:
            query: 自然语言问题（如"茅台毛利率变化原因"）
            top_k: 返回的检索结果数

        返回:
            {
                "found": True/False,
                "insights": ["要点1", "要点2"],    # LLM提炼的关键信息
                "quotations": [{"text": "...", "source": "xxx.pdf", "page": 9}, ...],
                "raw_chunks": [...],               # 完整检索结果
                "confidence": 0.0-1.0,
            }
        """
        logger.info(f"RAGContext 工具调用: {query}")

        # Step 1: Query 处理
        from rag.query_processor import process_query
        processed = process_query(query)

        # Step 2: 混合检索
        from rag.hybrid_search import hybrid_search
        sources = hybrid_search(processed, top_k=top_k)

        if not sources:
            return {
                "found": False,
                "insights": [],
                "quotations": [],
                "raw_chunks": [],
                "summary": f"未在知识库中找到与「{query}」相关的内容",
                "confidence": 0.0,
            }

        # Step 3: 提取关键引用
        quotations = []
        for s in sources[:top_k]:
            text = s["content"][:500].strip()
            if text:
                quotations.append({
                    "text": text,
                    "source": s.get("source", ""),
                    "page": s.get("page", ""),
                })

        # Step 4: LLM 提炼关键信息
        insights = self._extract_insights(query, sources[:3])

        return {
            "found": True,
            "insights": insights,
            "quotations": quotations,
            "raw_chunks": [{"content": s["content"][:300], "source": s["source"], "page": s["page"]} for s in sources],
            "summary": f"检索到 {len(sources)} 个相关段落",
            "confidence": 0.85 if insights else 0.5,
        }

    def _extract_insights(self, query: str, sources: List[dict]) -> List[str]:
        """LLM 从检索结果中提炼 2-3 条关键信息"""
        if not sources:
            return []

        context = "\n\n".join(
            f"[来源{i+1}] {s.get('source','')} p{s.get('page','')}:\n{s['content'][:600]}"
            for i, s in enumerate(sources)
        )

        prompt = f"""从以下文档片段中，提炼与用户问题最相关的 2-3 条关键信息。
每条控制在 50 字以内，用原文的语言风格。如果文档中没有相关信息，返回空列表。

## 用户问题
{query}

## 文档片段
{context}

## 输出格式（JSON数组，不要其他文字）
["关键信息1", "关键信息2"]
"""

        try:
            from rag.model_router import chat, TaskType
            from utils.text import parse_llm_json
            messages = [{"role": "user", "content": prompt}]
            response = chat(messages, query=query, task_type=TaskType.SIMPLE)
            result = parse_llm_json(response)
            if isinstance(result, list):
                return result[:3]
        except Exception as e:
            logger.warning(f"RAG 提炼失败: {e}")

        return []
