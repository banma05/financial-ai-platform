"""
依赖注册中心 — 确保所有自注册模块被导入。

V9.1 设计原则：每个模块通过 `Container.register(key, factory)` 自注册。
此文件只负责触发模块导入（触发 import 即触发注册），不集中管理注册逻辑。

面试台词："Container 的去中心化设计是 V9.1 的关键决策——
  每个模块自己声明依赖，Container 不知道有哪些模块，
  但知道任何被 import 的模块都已经自注册了。"
"""

import logging
from di.container import Container

logger = logging.getLogger(__name__)


def register_all() -> None:
    """
    触发所有模块导入，激活各模块的 Container.register() 自注册。

    幂等：重复调用不会重复注册（Container.register 覆盖同一 key）。

    CI 兼容：重依赖不可用的模块在 import 时会因 ImportError 被跳过，
    不影响轻量测试的运行——这就是自注册相比中心化注册的核心优势。
    """

    # ── RAG 组件 ─────────────────────
    _try_import("rag.embedder")
    _try_import("rag.vector_store")

    # ── LLM 组件 ─────────────────────
    _try_import("rag.model_router")

    # ── Hybrid Search ────────────────
    _try_import("rag.hybrid_search")

    # ── Agent 核心 ───────────────────
    _try_import("agent.graph")

    # ── 参数注入器 ───────────────────
    _try_import("agent.tools.param_injection")

    # ── 基础设施 ─────────────────────
    _try_import("utils.redis_client")


def _try_import(module_name: str) -> None:
    """尝试导入模块，失败时记录警告但不阻断"""
    try:
        __import__(module_name)
    except ImportError as e:
        logger.debug(f"[DI] 跳过 {module_name}（缺少依赖: {e}）")
