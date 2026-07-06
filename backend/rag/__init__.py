# CUDA 预热：Windows 上提前初始化 CUDA 上下文，防止 CrossEncoder segfault
# Linux / CI 环境无 GPU，跳过此步骤（否则触发 torch/sentence_transformers 安装要求）
import sys as _sys
if _sys.platform == "win32":
    import sentence_transformers  # noqa: F401

from .loader import load_document
from .splitter import split_documents
from .vector_store import add_documents, search_similar, get_document_list, reset_database
from .retriever import rag_query
from .model_router import chat as routed_chat, classify as classify_task, chat_stream
from .hybrid_search import hybrid_search, bm25_search, semantic_search, lambda_mart_rerank, route_query
from .semantic_splitter import semantic_chunk_per_page
from .jieba_tokenizer import tokenize, tokenize_for_search, tokenize_docs
from .evaluator import (
    full_evaluation,
    evaluate_context_recall,
    evaluate_faithfulness,
    recall_at_k,
    precision_at_k,
    mrr,
    ndcg_at_k,
    evaluate_retrieval,
    batch_evaluate,
    get_latest_report,
    save_report,
)

__all__ = [
    "load_document",
    "split_documents",
    "add_documents",
    "search_similar",
    "get_document_list",
    "reset_database",
    "rag_query",
    "routed_chat",
    "classify_task",
    "hybrid_search",
    "bm25_search",
    "semantic_search",
    "lambda_mart_rerank",
    "route_query",
    "semantic_chunk_per_page",
    "tokenize",
    "tokenize_for_search",
    "tokenize_docs",
    "full_evaluation",
    "evaluate_context_recall",
    "evaluate_faithfulness",
    "recall_at_k",
    "precision_at_k",
    "mrr",
    "ndcg_at_k",
    "evaluate_retrieval",
    "batch_evaluate",
    "get_latest_report",
    "save_report",
]
