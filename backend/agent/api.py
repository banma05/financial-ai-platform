"""
Agent 模块公共 API

所有对外接口集中定义于此。轻量依赖即时导入，
重依赖（graph → langgraph / planner → rag → sentence_transformers）
通过惰性加载避免 CI 环境炸链。

对外接口：
- run_agent_stream(): 流式执行（SSE），用于前端实时展示
- run_agent_sync(): 同步执行，返回完整结果
- FORMULA_REGISTRY: 15+ 财务公式注册表（即时导入，纯 Python）
- BUILTIN_TEMPLATES: 预设分析模板（见 agent/__init__.py __getattr__，
  惰性加载 — planner → rag → sentence_transformers，CI 不可用）
"""
from .tools.financial_calc import FORMULA_REGISTRY

__all__ = [
    "FORMULA_REGISTRY",
    "run_agent_stream",
    "run_agent_sync",
]


def run_agent_stream(*args, **kwargs):
    """流式执行 Agent 分析（SSE）→ 惰性加载 graph.run_agent_stream"""
    from .graph import run_agent_stream as _run
    return _run(*args, **kwargs)


def run_agent_sync(*args, **kwargs):
    """同步执行 Agent 分析 → 惰性加载 graph.run_agent_sync"""
    from .graph import run_agent_sync as _run
    return _run(*args, **kwargs)
