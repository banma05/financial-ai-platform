"""
向量数据库模块 - ChromaDB 管理
"""
import threading
from pathlib import Path
from typing import List, Optional
from loguru import logger
from langchain_chroma import Chroma

from config import CHROMA_PERSIST_DIR
from .embedder import get_embedding_model


COLLECTION_NAME = "financial_docs"

_chroma_store: Optional[Chroma] = None
_chroma_lock = threading.Lock()


def _get_chroma() -> Chroma:
    """获取 Chroma 实例（线程安全懒加载）"""
    global _chroma_store
    if _chroma_store is None:
        with _chroma_lock:
            if _chroma_store is None:
                _chroma_store = Chroma(
                    collection_name=COLLECTION_NAME,
                    embedding_function=get_embedding_model(),
                    persist_directory=CHROMA_PERSIST_DIR,
                )
    return _chroma_store


def add_documents(chunks: List[dict]) -> int:
    """
    将文本块存入向量数据库。

    参数:
        chunks: [{"content": "...", "source": "...", "page": 1}, ...]
    返回:
        存入的块数量
    """
    if not chunks:
        return 0

    texts = [c["content"] for c in chunks]
    metadatas = [
        {
            "source": c["source"],
            "page": c["page"],
            "chunk_type": c.get("chunk_type", "text"),
            "entity": c.get("entity", ""),
        }
        for c in chunks
    ]
    ids = [f"{c['source']}_p{c['page']}_{i}" for i, c in enumerate(chunks)]

    chroma = _get_chroma()
    chroma.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    logger.info(f"向量库新增 {len(chunks)} 个文本块")

    # 文档变更 → 使 BM25 缓存失效
    from .hybrid_search import _invalidate_bm25_cache
    _invalidate_bm25_cache()

    return len(chunks)


def search_similar(
    query: str,
    top_k: int = 5,
    filter_source: Optional[str] = None,
) -> List[dict]:
    """语义搜索"""
    chroma = _get_chroma()
    filter_dict = {"source": filter_source} if filter_source else None
    results = chroma.similarity_search_with_score(query, k=top_k, filter=filter_dict)
    return [
        {
            "content": doc.page_content,
            "source": doc.metadata.get("source", ""),
            "page": doc.metadata.get("page", 0),
            "score": float(score),
        }
        for doc, score in results
    ]


def get_document_list() -> List[dict]:
    """获取已索引的文档列表"""
    chroma = _get_chroma()
    collection = chroma._collection
    result = collection.get(include=["metadatas"])
    if not result["ids"]:
        return []

    from collections import defaultdict
    doc_stats = defaultdict(lambda: {"pages": set(), "chunk_count": 0})
    for meta in result["metadatas"]:
        source = meta.get("source", "unknown")
        page = meta.get("page", 0)
        doc_stats[source]["pages"].add(page)
        doc_stats[source]["chunk_count"] += 1

    return [
        {
            "filename": source,
            "chunk_count": stats["chunk_count"],
            "page_count": len(stats["pages"]),
        }
        for source, stats in doc_stats.items()
    ]


def delete_document(source: str) -> bool:
    """按 source 文件名删除文档的所有 chunks"""
    chroma = _get_chroma()
    collection = chroma._collection
    result = collection.get(where={"source": source})
    if result["ids"]:
        collection.delete(ids=result["ids"])
        logger.info(f"已删除文档: {source} ({len(result['ids'])} chunks)")
        from .hybrid_search import _invalidate_bm25_cache
        _invalidate_bm25_cache()
        return True
    return False


def reset_database():
    """清空向量数据库（开发调试用）"""
    global _chroma_store
    import shutil

    if _chroma_store is not None:
        try:
            _chroma_store._client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        _chroma_store = None

    persist_dir = Path(CHROMA_PERSIST_DIR)
    if persist_dir.exists():
        shutil.rmtree(str(persist_dir), ignore_errors=True)
