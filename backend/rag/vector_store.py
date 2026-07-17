"""
向量数据库模块 - ChromaDB 管理
"""
import atexit
import threading
from pathlib import Path
from typing import List, Optional
from loguru import logger
from langchain_chroma import Chroma

from config import CHROMA_PERSIST_DIR
from .embedder import get_embedding_model


COLLECTION_NAME = "financial_docs"

# Chroma 实例缓存
_chroma_store: Optional[Chroma] = None
_chroma_client = None  # 底层 PersistentClient，用于关闭
_chroma_lock = threading.Lock()


def _cleanup_chroma():
    """进程退出时释放 ChromaDB 引用（不主动关闭，让 Rust Drop 自然清理）"""
    global _chroma_store, _chroma_client
    # 注意: 不调用 _system.stop()！
    # 它会立即杀死 Rust runtime，中断后台 HNSW compaction，导致 segment 文件损坏。
    # 让 Python GC 和 Rust Drop trait 自然释放资源即可。
    _chroma_store = None
    _chroma_client = None


# 注册进程退出时的清理钩子
atexit.register(_cleanup_chroma)


def _get_chroma() -> Chroma:
    """获取 Chroma 实例（线程安全懒加载）"""
    global _chroma_store, _chroma_client
    if _chroma_store is None:
        with _chroma_lock:
            if _chroma_store is None:
                import chromadb
                _chroma_client = chromadb.PersistentClient(
                    path=CHROMA_PERSIST_DIR,
                    settings=chromadb.Settings(
                        anonymized_telemetry=False,
                        allow_reset=True,
                    ),
                )
                _chroma_store = Chroma(
                    client=_chroma_client,
                    collection_name=COLLECTION_NAME,
                    embedding_function=get_embedding_model(),
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
    """清空向量数据库（用于开发调试时重置）

    采用物理删除策略：先删 collection → 再清持久化目录 → 重建
    仅调用 delete_collection() 不够可靠，旧数据可能残留
    """
    global _chroma_store
    import gc
    import shutil

    # 1. 删除 ChromaDB collection
    if _chroma_store is not None:
        try:
            client = _chroma_store._client
            client.delete_collection(COLLECTION_NAME)
        except Exception as e:
            logger.debug(f"delete_collection 异常（可忽略）: {e}")
        _chroma_store = None

    # 2. 物理删除持久化目录（确保旧数据彻底清除）
    persist_dir = Path(CHROMA_PERSIST_DIR)
    if persist_dir.exists():
        try:
            shutil.rmtree(persist_dir)
        except Exception as e:
            logger.warning(f"删除持久化目录失败: {e}")
            # 备用方案：逐个删除子文件
            for item in persist_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as e:
                    logger.warning(f"删除持久化目录失败: {e}")

    gc.collect()

    # 3. 重建（触发懒加载，创建全新 collection）
    _get_chroma()


def delete_document(source_name: str) -> int:
    """
    按文档名删除向量库中的 chunks。

    返回: 删除的 chunk 数量
    """
    store = _get_chroma()
    try:
        results = store.get(where={"source": source_name})
        ids = results.get("ids", [])
        if ids:
            store.delete(ids=ids)
            logger.info(f"已删除文档「{source_name}」: {len(ids)} chunks")
        return len(ids)
    except Exception as e:
        logger.warning(f"删除文档「{source_name}」失败: {e}")
        return 0
