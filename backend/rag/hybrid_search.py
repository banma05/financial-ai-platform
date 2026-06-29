"""
混合检索 + LambdaMART 统一打分 + 策略路由

三、混合检索：
- 向量 + BM25 混合召回
- LambdaMART 统一打分维度（Cross-Encoder 实现，架构预留 LambdaMART）
- 策略路由分流：简单问题直接向量检索，复杂问题才重排序
"""
from typing import List, Tuple
from loguru import logger
from rank_bm25 import BM25Okapi

from .embedder import get_embedding_model
from .vector_store import _get_chroma


# ============ 策略路由 ============

# 复杂 query 关键词（触发完整混合检索 + 重排序）
COMPLEX_PATTERNS = [
    "分析", "对比", "趋势", "变化", "原因", "为什么",
    "异常", "风险", "评估", "判断", "预测", "建议",
    "关联", "影响", "差异", "波动",
    "指标", "比率", "毛利率", "净利率", "ROE", "ROA",
    "同比", "环比", "财务", "审计", "合规",
]


def route_query(query: str) -> str:
    """
    策略路由：判断问题复杂度，决定检索策略

    simple → 仅向量检索（快，省计算）
    complex → 完整混合检索 + 重排序（准，多花 1-2s）
    """
    for pattern in COMPLEX_PATTERNS:
        if pattern in query:
            logger.info(f"检索路由: complex（命中 '{pattern}'）→ 混合检索 + 重排序")
            return "complex"
    logger.info(f"检索路由: simple → 仅向量检索")
    return "simple"


# ============ BM25 关键词检索 ============

def _build_bm25_index():
    chroma = _get_chroma()
    data = chroma.get()
    if not data["documents"]:
        return None, [], []
    tokenized = [list(doc) for doc in data["documents"]]
    bm25 = BM25Okapi(tokenized)
    return bm25, data["documents"], data["metadatas"]


def bm25_search(query: str, top_k: int = 10) -> List[dict]:
    bm25, docs, metas = _build_bm25_index()
    if bm25 is None:
        return []
    tokenized_query = list(query)
    scores = bm25.get_scores(tokenized_query)
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
    from .vector_store import search_similar
    return search_similar(query, top_k=top_k)


# ============ RRF 融合 ============

def reciprocal_rank_fusion(
    bm25_results: List[dict],
    semantic_results: List[dict],
    k: int = 60,
) -> List[dict]:
    """
    RRF（Reciprocal Rank Fusion）
    score(d) = sum( 1 / (k + rank_i(d)) )
    不需要归一化，对不同尺度的分数鲁棒
    """
    fused = {}
    for rank, item in enumerate(bm25_results, start=1):
        key = item["content"][:100]
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
    return sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)


# ============ LambdaMART 统一打分 ============

_reranker = None


def _get_lambda_mart():
    """
    LambdaMART 统一打分器

    实际实现：Cross-Encoder Reranker（bge-reranker-v2-m3）
    架构设计：预留 LambdaMART 接口，当积累足够标注数据后可替换

    Cross-Encoder vs Bi-Encoder：
    - Bi-Encoder（Embedding）：query 和 doc 分别编码，快但粗糙
    - Cross-Encoder（Reranker）：query+doc 拼接编码，准但慢
    - 工程实践：粗排用 Bi-Encoder，精排用 Cross-Encoder

    LambdaMART 替换条件：
    - 需要 500+ 条 query-doc 相关性标注（0-4 分）
    - 训练后 LambdaMART 比 Cross-Encoder 快 10x，精度接近
    - 特征维度：BM25 分数、语义相似度、文档长度、词重叠率等
    """
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        import os
        local_path = os.path.join("data", "models", "BAAI", "bge-reranker-v2-m3")
        model_name = local_path if os.path.exists(local_path) else "BAAI/bge-reranker-v2-m3"
        _reranker = CrossEncoder(model_name)
        logger.info(f"LambdaMART（Cross-Encoder）已加载: {model_name}")
    return _reranker


def lambda_mart_rerank(query: str, candidates: List[dict], top_k: int = 5) -> List[dict]:
    """
    LambdaMART 统一打分：将 BM25 召回 + 语义召回的候选集
    用 Cross-Encoder 统一重新打分，消除双路检索的分数尺度差异

    设计思路：RRF 只看排名不看内容，
    LambdaMART（Cross-Encoder）把 query 和 doc 拼在一起深度打分，更准
    """
    if not candidates:
        return []

    try:
        model = _get_lambda_mart()
        pairs = [[query, c["content"]] for c in candidates]
        scores = model.predict(pairs)

        for item, score in zip(candidates, scores):
            item["rerank_score"] = float(score)

        ranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0), reverse=True)
        logger.info(f"LambdaMART 统一打分 Top-{top_k}, 最高分: {ranked[0].get('rerank_score', 0):.4f}")
        return ranked[:top_k]
    except Exception as e:
        logger.warning(f"LambdaMART 不可用，回退 RRF: {e}")
        return candidates[:top_k]


# ============ 完整检索入口 ============

def hybrid_search(
    query: str,
    top_k: int = 5,
    force_rerank: bool = False,
) -> List[dict]:
    """
    混合检索完整流程（带策略路由）

    simple → BM25 + 语义 → RRF 融合（快，~1s）
    complex → BM25 + 语义 → RRF → LambdaMART（准，+12s）

    参数:
        query: 用户问题
        top_k: 最终返回文档数
        force_rerank: 强制启用 LambdaMART

    返回:
        [{"content": "...", "source": "...", "page": 1, "score": 0.95}, ...]
    """
    strategy = route_query(query)

    # 并行召回
    bm25_results = bm25_search(query, top_k=10)
    semantic_results = semantic_search(query, top_k=10)

    # RRF 融合
    fused = reciprocal_rank_fusion(bm25_results, semantic_results)

    # 决定是否 LambdaMART 精排
    use_rerank = force_rerank or (strategy == "complex" and len(fused) > top_k)

    if use_rerank:
        final = lambda_mart_rerank(query, fused, top_k=top_k)
        logger.info(
            f"混合检索(重排): BM25 {len(bm25_results)} + 语义 {len(semantic_results)}"
            f" → RRF {len(fused)} → LambdaMART {len(final)}"
        )
    else:
        final = fused[:top_k]
        logger.info(
            f"混合检索(快速): BM25 {len(bm25_results)} + 语义 {len(semantic_results)}"
            f" → RRF {len(fused)} → Top-{len(final)}"
        )

    return final
