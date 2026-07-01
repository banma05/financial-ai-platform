"""
hybrid_search.py 单元测试

覆盖：策略路由、RRF 融合、LambdaMART 重排、混合检索集成
"""
from unittest.mock import patch, MagicMock

import pytest

from rag.hybrid_search import (
    route_query,
    SIMPLE_PATTERNS,
    COMPLEX_PATTERNS,
    reciprocal_rank_fusion,
    lambda_mart_rerank,
    hybrid_search,
    bm25_search,
    semantic_search,
)


# ============ 测试辅助 ============


def make_chunk(content: str, source: str = "test.pdf", page: int = 1, score: float = 1.0) -> dict:
    """快速构造测试用 chunk"""
    return {"content": content, "source": source, "page": page, "score": score}


# ============ route_query ============


class TestRouteQuery:
    """策略路由判断"""

    def test_简单问候_你好(self):
        assert route_query("你好") == "simple"

    def test_简单问候_帮助(self):
        assert route_query("帮助") == "simple"

    def test_简单问候_文档列表(self):
        assert route_query("文档列表") == "simple"

    def test_短query_无关键词_走simple(self):
        """短于 8 字符且无财务关键词 → simple"""
        assert route_query("你好啊") == "simple"
        assert route_query("谢谢") == "simple"

    def test_财务关键词_分析(self):
        """含"分析"关键词 → complex"""
        assert route_query("分析一下比亚迪的营收") == "complex"

    def test_财务关键词_对比(self):
        assert route_query("对比两家公司") == "complex"

    def test_财务关键词_ROE(self):
        assert route_query("ROE怎么算") == "complex"

    def test_财务关键词_增长(self):
        assert route_query("营收增长了多少") == "complex"

    def test_数值查询_多少(self):
        assert route_query("营收多少") == "complex"

    def test_默认中等长度无关键词_query走complex(self):
        """中等长度（≥8字）无明确关键词 → 默认 complex（财务场景对精度要求高）"""
        result = route_query("今年的财务情况")
        assert result == "complex"

    def test_SIMPLE_PATTERNS全部注册且互斥(self):
        """简单模式关键词不应出现在复杂列表中"""
        for sp in SIMPLE_PATTERNS:
            assert sp not in COMPLEX_PATTERNS, f"'{sp}' 不应同时在 SIMPLE 和 COMPLEX 中"

    def test_COMPLEX_PATTERNS全部非空(self):
        for cp in COMPLEX_PATTERNS:
            assert len(cp) > 0


# ============ reciprocal_rank_fusion ============


class TestReciprocalRankFusion:
    """RRF 融合"""

    def test_基本融合_去重(self):
        """相同内容的 chunk 应被合并"""
        bm25 = [make_chunk("内容A", "a.pdf", score=10.0)]
        semantic = [make_chunk("内容A", "a.pdf", score=0.9)]
        fused = reciprocal_rank_fusion(bm25, semantic, k=60)
        assert len(fused) == 1  # 重复内容合并

    def test_不同内容_不合并(self):
        bm25 = [make_chunk("内容A")]
        semantic = [make_chunk("内容B")]
        fused = reciprocal_rank_fusion(bm25, semantic, k=60)
        assert len(fused) == 2

    def test_排名越靠前_RRF分数越高(self):
        """同一个内容在两边排名不同，排名靠前的贡献更大"""
        bm25 = [make_chunk("内容A"), make_chunk("内容B")]
        semantic = [make_chunk("内容B"), make_chunk("内容A")]
        fused = reciprocal_rank_fusion(bm25, semantic, k=60)

        # 内容A: rank_bm25=1, rank_sem=2 → rrf = 1/(60+1) + 1/(60+2)
        # 内容B: rank_bm25=2, rank_sem=1 → rrf = 1/(60+2) + 1/(60+1)
        # 两者应相同
        a = next(c for c in fused if c["content"] == "内容A")
        b = next(c for c in fused if c["content"] == "内容B")
        assert a["rrf_score"] == pytest.approx(b["rrf_score"], abs=0.0001)

    def test_空列表(self):
        result = reciprocal_rank_fusion([], [])
        assert result == []

    def test_单边有结果(self):
        bm25 = [make_chunk("内容A")]
        fused = reciprocal_rank_fusion(bm25, [], k=60)
        assert len(fused) == 1
        assert fused[0]["rrf_score"] > 0

    def test_k值影响(self):
        """k 越小，排名差异影响越大"""
        chunks = [make_chunk(f"内容{i}") for i in range(3)]
        fused_k60 = reciprocal_rank_fusion(chunks[:1], chunks[1:2], k=60)
        fused_k1 = reciprocal_rank_fusion(chunks[:1], chunks[1:2], k=1)

        # k=1 时第一名和第二名分数差距更大
        # k=60: 1/(60+1)=0.01639
        # k=1:  1/(1+1)=0.5
        assert fused_k1[0]["rrf_score"] > fused_k60[0]["rrf_score"]

    def test_内容key取前100字符去重(self):
        """相同内容前100字符相同的 chunk 视为重复"""
        long_content = "X" * 100 + "后缀内容不同"
        bm25 = [{"content": long_content + "A", "source": "a.pdf", "score": 1.0}]
        semantic = [{"content": long_content + "B", "source": "b.pdf", "score": 2.0}]

        fused = reciprocal_rank_fusion(bm25, semantic, k=60)
        # 前100字符相同 → 视为同一文档
        assert len(fused) == 1


# ============ lambda_mart_rerank（mock）============


class TestLambdaMARTRerank:
    """LambdaMART 精排"""

    def test_空候选集(self):
        result = lambda_mart_rerank("query", [], top_k=5)
        assert result == []

    def test_基本重排(self):
        """mock CrossEncoder 返回的分数"""
        candidates = [
            make_chunk("财报营收100亿", "a.pdf"),
            make_chunk("公司成立于2000年", "b.pdf"),
            make_chunk("毛利率达到50%", "c.pdf"),
        ]
        with patch("rag.hybrid_search._get_lambda_mart") as mock_model:
            mock_reranker = MagicMock()
            # 模拟 CrossEncoder 对 [query, doc] pair 的打分
            mock_reranker.predict.return_value = [3.5, 1.2, 5.8]
            mock_model.return_value = mock_reranker

            result = lambda_mart_rerank("营收多少", candidates, top_k=3)

        assert len(result) == 3
        # 按 rerank_score 降序：5.8 → 3.5 → 1.2
        assert result[0]["content"] == "毛利率达到50%"
        assert result[0]["rerank_score"] == 5.8
        assert result[-1]["content"] == "公司成立于2000年"

    def test_top_k限制(self):
        """只返回 top_k 个结果"""
        candidates = [make_chunk(f"内容{i}") for i in range(10)]
        with patch("rag.hybrid_search._get_lambda_mart") as mock_model:
            mock_reranker = MagicMock()
            mock_reranker.predict.return_value = list(range(10, 0, -1))
            mock_model.return_value = mock_reranker

            result = lambda_mart_rerank("query", candidates, top_k=3)
        assert len(result) == 3

    def test_模型异常回退RRF(self):
        """CrossEncoder 加载失败时回退到原始候选集 top_k"""
        candidates = [make_chunk(f"内容{i}") for i in range(5)]
        with patch("rag.hybrid_search._get_lambda_mart", side_effect=Exception("模型文件丢失")):
            result = lambda_mart_rerank("query", candidates, top_k=3)
        assert len(result) == 3  # 回退：取前 top_k


# ============ bm25_search（mock ChromaDB）============


class TestBM25Search:
    """BM25 关键词检索"""

    def test_基本检索(self):
        """mock ChromaDB 返回文档列表"""
        mock_data = {
            "documents": ["营收达到100亿", "公司成立", "毛利率50%"],
            "metadatas": [
                {"source": "a.pdf", "page": 1},
                {"source": "b.pdf", "page": 2},
                {"source": "a.pdf", "page": 5},
            ],
        }
        with patch("rag.hybrid_search._get_chroma") as mock_chroma:
            mock_chroma.return_value.get.return_value = mock_data
            results = bm25_search("营收", top_k=3)

        assert len(results) > 0
        for r in results:
            assert "content" in r
            assert "source" in r
            assert "score" in r

    def test_空数据库(self):
        with patch("rag.hybrid_search._get_chroma") as mock_chroma:
            mock_chroma.return_value.get.return_value = {"documents": None}
            results = bm25_search("营收", top_k=5)
        assert results == []

    def test_文档过滤(self):
        """filter_sources 生效"""
        mock_data = {
            "documents": ["营收100亿", "净利润50亿"],
            "metadatas": [
                {"source": "a.pdf", "page": 1},
                {"source": "b.pdf", "page": 2},
            ],
        }
        with patch("rag.hybrid_search._get_chroma") as mock_chroma:
            mock_chroma.return_value.get.return_value = mock_data
            results = bm25_search("营收", top_k=5, filter_sources=["a.pdf"])

        assert all(r["source"] == "a.pdf" for r in results)

    def test_top_k限制(self):
        mock_data = {
            "documents": [f"文档{i}" for i in range(20)],
            "metadatas": [{"source": "a.pdf", "page": i} for i in range(20)],
        }
        with patch("rag.hybrid_search._get_chroma") as mock_chroma:
            mock_chroma.return_value.get.return_value = mock_data
            results = bm25_search("文档", top_k=5)
        assert len(results) <= 5


# ============ semantic_search（mock ChromaDB）============


class TestSemanticSearch:
    """语义检索"""

    def test_基本检索(self):
        """普通语义检索，mock vector_store 层"""
        with patch("rag.vector_store.search_similar") as mock_search:
            mock_search.return_value = [make_chunk("语义匹配内容")]
            results = semantic_search("测试query", top_k=5)
        assert len(results) == 1

    def test_有文档过滤(self):
        """filter_sources 时逐个文档搜索再合并"""
        with patch("rag.vector_store.search_similar") as mock_search:
            mock_search.side_effect = lambda query, top_k, filter_source: (
                [make_chunk(f"来自{filter_source}", filter_source)]
            )
            results = semantic_search("test", top_k=5, filter_sources=["a.pdf", "b.pdf"])
        assert len(results) == 2


# ============ hybrid_search（集成流程，mock 全部依赖）============


class TestHybridSearch:
    """混合检索完整流程"""

    def test_simple路由_快速模式(self):
        """简单 query 走快速模式（RRF 不重排）"""
        with patch("rag.hybrid_search.bm25_search", return_value=[make_chunk("你好", "a.pdf")]):
            with patch("rag.hybrid_search.semantic_search", return_value=[make_chunk("你好", "a.pdf")]):
                with patch("rag.hybrid_search.lambda_mart_rerank") as mock_rerank:
                    result = hybrid_search("你好", top_k=5)

        assert len(result) > 0
        mock_rerank.assert_not_called()  # simple 路由不触发重排

    def test_complex路由_重排模式(self):
        """复杂 query 触发 LambdaMART——需要 fused 结果数 > top_k"""
        with patch("rag.hybrid_search.bm25_search", return_value=[
            make_chunk("营收分析数据1", "a.pdf"),
            make_chunk("营收分析数据2", "b.pdf"),
            make_chunk("营收分析数据3", "c.pdf"),
            make_chunk("营收分析数据4", "d.pdf"),
        ]):
            with patch("rag.hybrid_search.semantic_search", return_value=[
                make_chunk("语义结果1", "e.pdf"),
                make_chunk("语义结果2", "f.pdf"),
            ]):
                with patch("rag.hybrid_search.lambda_mart_rerank") as mock_rerank:
                    mock_rerank.return_value = [make_chunk("营收分析数据1", "a.pdf")]
                    result = hybrid_search("分析营收趋势", top_k=5)

        # strategy=complex, fused 6 个 > top_k=5 → 触发重排
        mock_rerank.assert_called_once()

    def test_force_rerank_强制重排(self):
        """force_rerank=True 时无论简单/复杂都走重排"""
        with patch("rag.hybrid_search.bm25_search", return_value=[make_chunk("你好", "a.pdf")]):
            with patch("rag.hybrid_search.semantic_search", return_value=[make_chunk("你好", "a.pdf")]):
                with patch("rag.hybrid_search.lambda_mart_rerank") as mock_rerank:
                    mock_rerank.return_value = [make_chunk("你好", "a.pdf")]
                    result = hybrid_search("你好", top_k=5, force_rerank=True)

        mock_rerank.assert_called_once()

    def test_实体路由_自动升级为complex(self):
        """实体路由命中时，simple query 自动升级为 complex"""
        with patch("rag.hybrid_search.bm25_search", return_value=[
            make_chunk("内容A", "比亚迪2024年年报.PDF"),
            make_chunk("内容B", "比亚迪2024年年报.PDF"),
            make_chunk("内容C", "比亚迪2024年年报.PDF"),
            make_chunk("内容D", "比亚迪2024年年报.PDF"),
        ]):
            with patch("rag.hybrid_search.semantic_search", return_value=[
                make_chunk("内容E", "比亚迪2024年年报.PDF"),
                make_chunk("内容F", "比亚迪2024年年报.PDF"),
            ]):
                with patch("rag.hybrid_search.lambda_mart_rerank") as mock_rerank:
                    mock_rerank.return_value = [make_chunk("内容A", "比亚迪2024年年报.PDF")]
                    with patch("rag.hybrid_search.resolve_document_filter", return_value=["比亚迪2024年年报.PDF"]):
                        result = hybrid_search("营收", top_k=5, enable_entity_routing=True)

        # 实体路由命中 + fused 6 > top_k 5 → 触发重排
        mock_rerank.assert_called_once()

    def test_filter_sources_传入(self):
        """显式传入 filter_sources"""
        with patch("rag.hybrid_search.bm25_search", return_value=[make_chunk("数据", "a.pdf")]):
            with patch("rag.hybrid_search.semantic_search", return_value=[make_chunk("数据", "a.pdf")]):
                result = hybrid_search("数据", top_k=5, filter_sources=["a.pdf"])
        assert all(r["source"] == "a.pdf" for r in result)

    def test_空结果_不抛异常(self):
        """两边检索都无结果时不抛异常"""
        with patch("rag.hybrid_search.bm25_search", return_value=[]):
            with patch("rag.hybrid_search.semantic_search", return_value=[]):
                result = hybrid_search("不存在的query", top_k=5)
        assert result == []
