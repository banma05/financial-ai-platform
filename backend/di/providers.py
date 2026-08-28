"""
依赖注册中心 — 确保所有自注册模块被导入。

V9.1 设计原则：每个模块通过 `Container.register(key, factory)` 自注册。
此文件只负责触发模块导入（触发 import 即触发注册），不集中管理注册逻辑。

面试台词："Container 的去中心化设计是 V9.1 的关键决策——
  每个模块自己声明依赖，Container 不知道有哪些模块，
  但知道任何被 import 的模块都已经自注册了。"
"""

import sys
import importlib
import logging
from di.container import Container

logger = logging.getLogger(__name__)

# 各模块在顶层通过 Container.register() 自注册。此列表是 register_all 的导入清单，
# 也是容器被 reset() 清空后需要 reload 强制重注册的目标模块。
_REGISTER_MODULES = [
    "rag.embedder",
    "rag.vector_store",
    "rag.model_router",
    "rag.hybrid_search",
    "agent.graph",
    "agent.tools.param_injection",
    "utils.redis_client",
]


def register_all(force: bool = False) -> None:
    """
    触发所有模块导入，激活各模块的 Container.register() 自注册。

    幂等：重复调用不会重复注册（Container.register 覆盖同一 key）。

    force=True（测试中容器被 reset() 后使用）：
      自注册依赖模块首次 import 的副作用。reset() 清空容器后，模块已被
      sys.modules 缓存，普通 __import__ 不会重新执行模块顶层自注册。
      force 模式对已加载模块执行 importlib.reload，强制重新执行
      Container.register()，保证容器恢复完整注册。所有注册项均为惰性
      factory（实例在 resolve 时才创建），reload 只重新定义 factory，
      不加载任何重资源，安全。

    CI 兼容：重依赖不可用的模块在 import 时会因 ImportError 被跳过，
    不影响轻量测试的运行——这就是自注册相比中心化注册的核心优势。
    """
    for module_name in _REGISTER_MODULES:
        _try_import(module_name, force=force)


def _try_import(module_name: str, force: bool = False) -> None:
    """尝试导入模块，失败时记录警告但不阻断"""
    try:
        if force and module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        else:
            __import__(module_name)
    except ImportError as e:
        logger.debug(f"[DI] 跳过 {module_name}（缺少依赖: {e}）")
