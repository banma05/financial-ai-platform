"""依赖注入模块 — V9.1 架构核心"""

from .container import Container
from .providers import register_all

__all__ = ["Container", "register_all"]
