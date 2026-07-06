"""
数据分析 Agent 模块（模块二）

核心功能：
- NL 驱动数据查询：自然语言 → 检索 + 结构提取
- 财务指标计算：15+ 内置公式库
- 可视化图表：5 种图表类型（折线/柱状/饼图/雷达/双轴）
- 分析报告：自动组装 Markdown 报告 + LLM 洞察

公共 API 定义在 api.py，此处做重导出 + 惰性加载兼容。
"""
from .api import FORMULA_REGISTRY, run_agent_stream, run_agent_sync


def __getattr__(name):
    """
    惰性加载 BUILTIN_TEMPLATES。

    原因：planner → rag.model_router → rag/__init__.py → sentence_transformers，
    CI 环境无 GPU/ChromaDB 依赖，必须延迟到实际访问时才导入。
    """
    if name == "BUILTIN_TEMPLATES":
        from .planner import BUILTIN_TEMPLATES
        return BUILTIN_TEMPLATES
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
