"""
向量数据库模块 - ChromaDB 管理
"""
import shutil
from pathlib import Path
from typing import List, Optional
from loguru import logger
from langchain_chroma import Chroma

from config import CHROMA_PERSIST_DIR
from .embedder import get_embedding_model


COLLECTION_NAME = "financial_docs"

# Chroma 实例缓存
_chroma_store: Optional[Chroma] = None


def _get_chroma() -> Chroma:
    """获取 Chroma 实例（懒加载）"""
    global _chroma_store
    if _chroma_store is None:
        _chroma_store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embedding_model(),
            persist_directory=CHROMA_PERSIST_DIR,
        )
    return _chroma_store


def add_documents(chunks: List[dict]) -> int:
    """
    将文本块存入向量数据库

    参数:
        chunks: [{"content": "...", "source": "...", "page": 1}, ...]

    返回:
        存入的块数量
    """
    if not chunks:
        return 0

    texts = [c["content"] for c in chunks]
    metadatas = [{"source": c["source"], "page": c["page"]} for c in chunks]
    ids = [f"{c['source']}_p{c['page']}_{i}" for i, c in enumerate(chunks)]

    chroma = _get_chroma()
    chroma.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    logger.info(f"向量库新增 {len(chunks)} 个文本块")
    return len(chunks)


def search_similar(
    query: str,
    top_k: int = 5,
    filter_source: Optional[str] = None,
) -> List[dict]:
    """
    检索与 query 最相似的文本块

    返回:
        [{"content": "...", "source": "...", "page": 1, "score": 0.95}, ...]
    """
    chroma = _get_chroma()
    search_filter = {"source": filter_source} if filter_source else None

    results = chroma.similarity_search_with_score(
        query=query,
        k=top_k,
        filter=search_filter,
    )

    return [
        {
            "content": doc.page_content,
            "source": doc.metadata.get("source", ""),
            "page": doc.metadata.get("page", 1),
            "score": round(score, 4),
        }
        for doc, score in results
    ]


def get_document_list() -> List[dict]:
    """获取已存入的文档列表及统计"""
    chroma = _get_chroma()
    # Chroma 的 get() 返回所有数据
    all_data = chroma.get()
    if not all_data["metadatas"]:
        return []

    # 按 source 聚合统计
    doc_stats = {}
    for meta in all_data["metadatas"]:
        source = meta.get("source", "unknown")
        if source not in doc_stats:
            doc_stats[source] = {"chunk_count": 0, "pages": set()}
        doc_stats[source]["chunk_count"] += 1
        doc_stats[source]["pages"].add(meta.get("page", 1))

    return [
        {
            "filename": source,
            "chunk_count": stats["chunk_count"],
            "page_count": len(stats["pages"]),
        }
        for source, stats in doc_stats.items()
    ]


def reset_database():
    """清空向量数据库（用于开发调试时重置）"""
    global _chroma_store
    _chroma_store = None
    persist_path = Path(CHROMA_PERSIST_DIR)
    if persist_path.exists():
        shutil.rmtree(persist_path)
        persist_path.mkdir(parents=True, exist_ok=True)
    logger.warning("向量数据库已重置")
