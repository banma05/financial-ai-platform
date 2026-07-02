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
from .graph import run_agent_stream, run_agent_sync
from .planner import BUILTIN_TEMPLATES
from .tools.financial_calc import FORMULA_REGISTRY

__all__ = [
    "run_agent_stream",
    "run_agent_sync",
    "BUILTIN_TEMPLATES",
    "FORMULA_REGISTRY",
]
