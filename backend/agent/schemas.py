"""
Agent 专用 Pydantic 数据模型（模块二）
"""
from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel, Field


# ============ 任务相关模型 ============

TaskType = Literal[
    "data_query", "calculate", "chart", "analyze", "compare",
    "mcp_stock_price", "mcp_financial_statements", "mcp_calculate_ratio",
    "mcp_industry_comparison", "mcp_market_index", "mcp_financial_calendar",
]


class AnalysisTask(BaseModel):
    """Planner 输出的单个子任务"""
    task_id: str = Field(..., description="任务 ID，从 1 开始递增")
    task_type: TaskType = Field(..., description="任务类型")
    description: str = Field(..., description="人类可读的任务描述")
    params: Dict[str, Any] = Field(default_factory=dict, description="工具调用参数")
    depends_on: List[str] = Field(default_factory=list, description="依赖的任务 ID 列表")
    status: str = Field(default="pending", description="pending / running / completed / failed")


class TaskResult(BaseModel):
    """单个任务的执行结果"""
    task_id: str
    task_type: str
    success: bool
    summary: str = ""                          # 人类可读的结果摘要
    data: Any = None                           # 结构化数据（数值/字典等）
    chart_base64: Optional[str] = None         # 图表 base64 编码（图表任务专用）
    error: Optional[str] = None                # 失败时的错误信息


class AnalysisPlan(BaseModel):
    """Planner 输出的完整分析计划"""
    tasks: List[AnalysisTask] = Field(default_factory=list)
    requires_clarification: Optional[str] = None  # None=不需追问，str=追问内容


# ============ 图表配置模型 ============

ChartType = Literal["line", "bar", "pie", "radar", "dual_axis"]


class ChartConfig(BaseModel):
    """图表生成配置"""
    chart_type: ChartType = Field(..., description="图表类型")
    title: str = Field(..., description="图表标题")
    data: Dict[str, Any] = Field(default_factory=dict, description="图表数据")
    x_label: str = Field(default="", description="X 轴标签")
    y_label: str = Field(default="", description="Y 轴标签")


# 分析模板模型 → 已迁移至 models/schemas.py（TemplateInfo）
# API 请求/响应模型 → 已迁移至 models/schemas.py（AgentRequest/AgentResponse）
# 此处只保留 Agent 内部编排所需的数据模型（AnalysisTask/TaskResult/AnalysisPlan/ChartConfig）


class ClarifyRequest(BaseModel):
    """追问回复请求"""
    query: str = Field(..., description="用户对追问的回答")
    session_id: str = Field(default="default")
