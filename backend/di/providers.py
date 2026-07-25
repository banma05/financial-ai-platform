"""
依赖注册中心 — 所有应用级组件的工厂注册。

在应用启动时调用 register_all() 一次，之后所有组件通过
Container.resolve(key) 获取，享受线程安全的惰性初始化。

面试台词："14 个全局单例的注册全部集中在这个文件里。
  一眼就能看清整个应用的依赖关系图。"
"""

from di.container import Container


def register_all() -> None:
    """注册所有应用级单例（幂等，重复调用覆盖而非重复创建）"""

    # ── RAG 组件 ─────────────────────
    from rag.embedder import _create_embedding_model
    from rag.vector_store import _create_chroma_store

    Container.register("embedding_model", _create_embedding_model)
    Container.register("chroma_store", _create_chroma_store)

    # ── LLM 组件 ─────────────────────
    from rag.model_router import _create_llm_client

    Container.register("llm_client", _create_llm_client)

    # ── Hybrid Search 组件 ───────────
    from rag.hybrid_search import _create_reranker

    Container.register("reranker", _create_reranker)

    # ── Agent 核心组件 ───────────────
    from agent.graph import (
        _create_tool_registry,
        _create_planner,
        _create_executor,
        _create_reporter,
        _create_agent_graph,
    )

    Container.register("tool_registry", _create_tool_registry)
    Container.register("planner", _create_planner)
    Container.register("executor", _create_executor)
    Container.register("reporter", _create_reporter)
    Container.register("agent_graph", _create_agent_graph)

    # ── 参数注入器 ───────────────────
    from agent.tools.param_injection import _create_param_injector

    Container.register("param_injector", _create_param_injector)

    # ── 基础设施 ─────────────────────
    from utils.redis_client import (
        _create_redis_client,
        _create_rate_limiter,
        _create_session_store,
    )

    Container.register("redis_client", _create_redis_client)
    Container.register("rate_limiter", _create_rate_limiter)
    Container.register("session_store", _create_session_store)

    # ── 重排序器降级缓存（可变容器，非单例对象）──
    Container.register("bm25_cache", dict)
