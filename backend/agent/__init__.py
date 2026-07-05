"""
数据分析 Agent 模块（模块二）

核心功能：
- NL 驱动数据查询：自然语言 → 检索 + 结构提取
- 财务指标计算：15+ 内置公式库
- 可视化图表：5 种图表类型（折线/柱状/饼图/雷达/双轴）
- 分析报告：自动组装 Markdown 报告 + LLM 洞察

对外接口：
- run_agent_stream(): 流式执行（SSE），用于前端实时展示
- run_agent_sync(): 同步执行，返回完整结果
- BUILTIN_TEMPLATES: 预设分析模板
"""

# 🔧 懒加载：避免 import agent 时触发 langgraph/rag/matplotlib 全家桶
# CI 环境只需 FORMULA_REGISTRY（纯 Python），不需要 graph 和 planner
from .tools.financial_calc import FORMULA_REGISTRY


def run_agent_stream(*args, **kwargs):
    from .graph import run_agent_stream as _run
    return _run(*args, **kwargs)


def run_agent_sync(*args, **kwargs):
    from .graph import run_agent_sync as _run
    return _run(*args, **kwargs)


def _get_templates():
    from .planner import BUILTIN_TEMPLATES as _t
    return _t


# 通过 __getattr__ 实现模块级懒加载（Python 3.7+）
def __getattr__(name):
    if name == "BUILTIN_TEMPLATES":
        from .planner import BUILTIN_TEMPLATES
        return BUILTIN_TEMPLATES
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
