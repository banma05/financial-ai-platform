"""
RAG 模块 — 知识库检索增强生成

所有子模块通过 __getattr__ 惰性加载——import rag 时不再触发全家桶依赖
（loader→pymupdf, vector_store→chromadb, hybrid_search→sentence_transformers）。
只在实际访问对应功能时才加载子模块，CI/CPU 环境不再被强制安装重依赖。
"""
import importlib

# GPU 预热：防止 HuggingFaceEmbeddings → CrossEncoder 混合设备初始化导致 segfault
# 已安装 sentence_transformers → 预初始化；未安装 → 静默跳过（CI/CPU 环境无需）
try:
    import sentence_transformers  # noqa: F401
except ImportError:
    pass

# 惰性加载映射：export_name → (module_name, attr_name)
# attr_name 为 None 表示与 export_name 同名
_MODULE_MAP = {
    # loader
    "load_document": (".loader", None),
    # splitter
    "split_documents": (".splitter", None),
    # vector_store
    "add_documents": (".vector_store", None),
    "search_similar": (".vector_store", None),
    "get_document_list": (".vector_store", None),
    "reset_database": (".vector_store", None),
    # retriever
    "rag_query": (".retriever", None),
    # model_router (有别名)
    "routed_chat": (".model_router", "chat"),
    "classify_task": (".model_router", "classify"),
    "chat_stream": (".model_router", None),
    # hybrid_search
    "hybrid_search": (".hybrid_search", None),
    "bm25_search": (".hybrid_search", None),
    "semantic_search": (".hybrid_search", None),
    "lambda_mart_rerank": (".hybrid_search", None),
    "route_query": (".hybrid_search", None),
    # semantic_splitter
    "semantic_chunk_per_page": (".semantic_splitter", None),
    # jieba_tokenizer
    "tokenize": (".jieba_tokenizer", None),
    "tokenize_for_search": (".jieba_tokenizer", None),
    "tokenize_docs": (".jieba_tokenizer", None),
    # evaluator
    "full_evaluation": (".evaluator", None),
    "evaluate_context_recall": (".evaluator", None),
    "evaluate_faithfulness": (".evaluator", None),
    "recall_at_k": (".evaluator", None),
    "precision_at_k": (".evaluator", None),
    "mrr": (".evaluator", None),
    "ndcg_at_k": (".evaluator", None),
    "evaluate_retrieval": (".evaluator", None),
    "batch_evaluate": (".evaluator", None),
    "get_latest_report": (".evaluator", None),
    "save_report": (".evaluator", None),
}


def __getattr__(name):
    """惰性加载子模块——只在首次访问时才 import。"""
    entry = _MODULE_MAP.get(name)
    if entry is not None:
        mod_name, attr_name = entry
        mod = importlib.import_module(mod_name, __package__)
        actual_attr = attr_name if attr_name else name
        attr = getattr(mod, actual_attr)
        # 缓存到模块全局，下次访问不走 __getattr__
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = list(_MODULE_MAP.keys())
