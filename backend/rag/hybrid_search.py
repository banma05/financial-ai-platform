"""
混合检索 + Reranker 重排序

BM25（关键词精确匹配）+ 语义搜索（BGE）→ RRF 融合 → BGE Reranker 精排

面试亮点：
- BM25 + 语义 = 互补检索
- RRF 融合算法（比加权求和更鲁棒）
- Reranker 做最后一道质量把关
"""
from typing import List
from loguru import logger
from rank_bm25 import BM25Okapi

from .embedder import get_embedding_model
from .vector_store import _get_chroma


def _build_bm25_index():
    """从 ChromaDB 中重建 BM25 索引"""
    chroma = _get_chroma()
    data = chroma.get()
    if not data["documents"]:
        return None, [], []
    # 分词（中文按字符级简单分词，生产环境可用 jieba）
    tokenized = [list(doc) for doc in data["documents"]]
    bm25 = BM25Okapi(tokenized)
    return bm25, data["documents"], data["metadatas"]


def bm25_search(query: str, top_k: int = 10) -> List[dict]:
    """BM25 关键词检索"""
    bm25, docs, metas = _build_bm25_index()
    if bm25 is None:
        return []

    tokenized_query = list(query)
    scores = bm25.get_scores(tokenized_query)

    # 按分数排序
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

    return [
        {
            "content": docs[i],
            "source": metas[i].get("source", ""),
            "page": metas[i].get("page", 1),
            "score": float(score),
        }
        for i, score in ranked
    ]


def semantic_search(query: str, top_k: int = 10) -> List[dict]:
    """语义向量检索"""
    from .vector_store import search_similar
    return search_similar(query, top_k=top_k)


def reciprocal_rank_fusion(
    bm25_results: List[dict],
    semantic_results: List[dict],
    k: int = 60,
) -> List[dict]:
    """
    RRF（Reciprocal Rank Fusion）融合算法

    原理：不直接加分数，而是用排名倒数加权
    score(d) = sum( 1 / (k + rank_i(d)) )  for each retriever i

    优势：不需要归一化分数，对不同尺度的分数鲁棒
    """
    fused = {}

    for rank, item in enumerate(bm25_results, start=1):
        key = item["content"][:100]  # 用前100字符做唯一标识
        if key not in fused:
            fused[key] = item.copy()
            fused[key]["rrf_score"] = 0
        fused[key]["rrf_score"] += 1 / (k + rank)

    for rank, item in enumerate(semantic_results, start=1):
        key = item["content"][:100]
        if key not in fused:
            fused[key] = item.copy()
            fused[key]["rrf_score"] = 0
        fused[key]["rrf_score"] += 1 / (k + rank)

    # 按 RRF 分数排序
    sorted_items = sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)
    return sorted_items


_reranker = None


def _get_reranker():
    """懒加载 Reranker（首次加载慢，后续调用快）"""
    global _reranker
    if _reranker is None:
        from FlagEmbedding import FlagReranker
        import os
        # 优先用 ModelScope 本地路径，其次 HuggingFace
        local_path = os.path.join("data", "models", "BAAI", "bge-reranker-v2-m3")
        model_name = local_path if os.path.exists(local_path) else "BAAI/bge-reranker-v2-m3"
        _reranker = FlagReranker(model_name, use_fp16=False, cache_dir="data/models")
        logger.info(f"Reranker 已加载: {model_name}")
    return _reranker


def rerank(query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
    """
    BGE Reranker 精排（Cross-Encoder，比 Embedding 更准）
    如果 Reranker 不可用则回退到 RRF 排序
    """
    if not candidates:
        return []

    try:
        reranker = _get_reranker()
        pairs = [[query, c["content"]] for c in candidates]
        scores = reranker.compute_score(pairs)
        for item, score in zip(candidates, scores):
            item["rerank_score"] = float(score)
        ranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
        logger.info(f"Reranker 精排 Top-{top_k}, 最高分: {ranked[0].get('rerank_score', 0):.4f}")
        return ranked[:top_k]
    except Exception as e:
        logger.warning(f"Reranker 暂不可用，回退 RRF: {e}")
        return candidates[:top_k]


def hybrid_search(
    query: str,
    top_k: int = 5,
    use_reranker: bool = True,
) -> List[dict]:
    """
    混合检索完整流程

    参数:
        query: 用户问题
        top_k: 最终返回文档数
        use_reranker: 是否启用 Reranker 精排

    返回:
        [{"content": "...", "source": "...", "page": 1, "score": 0.95}, ...]
    """
    # 第一步：并行检索
    logger.info("BM25 + 语义并行检索...")
    bm25_results = bm25_search(query, top_k=10)
    semantic_results = semantic_search(query, top_k=10)

    # 第二步：RRF 融合
    fused = reciprocal_rank_fusion(bm25_results, semantic_results)

    # 第三步：Reranker 精排
    if use_reranker and len(fused) > top_k:
        final = rerank(query, fused, top_k=top_k)
    else:
        final = fused[:top_k]

    logger.info(f"混合检索完成: BM25 {len(bm25_results)} + 语义 {len(semantic_results)} → 融合 {len(fused)} → 精排 {len(final)}")
    return final
