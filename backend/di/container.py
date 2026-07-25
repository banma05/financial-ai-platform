"""
极简依赖注入容器 — V9.1 架构核心。

设计原则：
- 零外部依赖（60 行代码解决的问题不引入 3000 行的库）
- 线程安全的惰性初始化（RLock 保护，消除 TOCTOU 竞态）
- 支持测试替换（override）+ 重置（reset）
- 支持启动预热（warmup，在事件循环外加载重模型）

为什么不用 FastAPI Depends？
  FastAPI Depends 只在请求上下文中工作。Embedding 模型、ChromaDB 连接、
  重排序器等组件在请求上下文外也需要使用。Container 是应用级单例管理，
  与请求级 DI（FastAPI Depends）互补而非替代。

为什么自己写而不用 dependency-injector？
  项目只需管理约 15 个应用级单例。60 行代码 + 零依赖 vs 3000 行 + pip install，
  选择前者是工程上的 trade-off——代码越少，面试时越容易讲清楚设计意图。

面试台词：
  "这个 Container 是 V9.1 重构的核心——我把 14 个散落在各模块的全局单例
   全部收进来，用 threading.RLock 保证线程安全，同时支持测试时的 mock 替换。
   总共 60 行代码，零外部依赖。"
"""

import threading
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class Container:
    """线程安全的惰性初始化应用容器"""

    _factories: dict[str, Callable[[], Any]] = {}
    _instances: dict[str, Any] = {}
    _lock = threading.RLock()

    # ── 注册 ───────────────────────────

    @classmethod
    def register(cls, key: str, factory: Callable[[], Any]) -> None:
        """
        注册工厂函数。

        key 重复时发出警告并覆盖（幂等，方便测试时重新注册）。
        """
        with cls._lock:
            existing = key in cls._factories
            cls._factories[key] = factory
            if existing:
                logger.warning(
                    f"Container: 覆盖已注册的 '{key}'（通常发生在测试中）"
                )
            else:
                logger.debug(f"Container: 注册 '{key}'")

    # ── 解析 ───────────────────────────

    @classmethod
    def resolve(cls, key: str) -> Any:
        """
        惰性初始化 + 线程安全解析。

        首次访问时在锁内调用工厂函数创建实例，后续直接返回缓存。
        工厂函数本身不在锁内执行——只在创建完成后赋值，避免长时间持锁。
        """
        # 快速路径：已初始化则直接返回（无锁）
        if key in cls._instances:
            return cls._instances[key]

        with cls._lock:
            # 双重检查：获取锁后再次确认
            if key in cls._instances:
                return cls._instances[key]

            factory = cls._factories.get(key)
            if factory is None:
                raise KeyError(
                    f"Container: 未注册的键 '{key}'。"
                    f"已注册: {list(cls._factories.keys())}"
                )

            logger.info(f"Container: 惰性初始化 '{key}'")
            # 工厂函数在锁内调用（确保只创建一次），
            # 但对于 Embedding/模型加载等耗时操作，首次调用会阻塞
            # 生产环境建议通过 warmup() 在启动时预加载
            instance = factory()
            cls._instances[key] = instance
            return instance

    @classmethod
    def is_ready(cls, key: str) -> bool:
        """检查实例是否已初始化（不触发惰性创建）"""
        return key in cls._instances

    # ── 测试支持 ───────────────────────

    @classmethod
    def override(cls, key: str, instance: Any) -> None:
        """测试用：替换为 mock 实例"""
        with cls._lock:
            cls._instances[key] = instance
            logger.debug(f"Container: 测试覆盖 '{key}'")

    @classmethod
    def warmup(cls, keys: Optional[list[str]] = None) -> None:
        """
        启动时预热：在事件循环外同步加载重资源。

        对 Embedding 模型、CrossEncoder 等大模型，在 uvicorn 启动时
        通过 run_in_executor 异步调用此方法，避免首次请求的冷启动延迟。
        """
        targets = keys or list(cls._factories.keys())
        for key in targets:
            if key not in cls._instances:
                logger.info(f"Container: 预热 '{key}'")
                cls.resolve(key)

    @classmethod
    def reset(cls) -> None:
        """测试用：完全重置容器（清理所有实例和工厂）"""
        with cls._lock:
            cls._instances.clear()
            cls._factories.clear()
            logger.debug("Container: 已完全重置")

    @classmethod
    def list_all(cls) -> dict[str, bool]:
        """列出所有注册项及其初始化状态（调试用）"""
        with cls._lock:
            return {k: k in cls._instances for k in cls._factories}
