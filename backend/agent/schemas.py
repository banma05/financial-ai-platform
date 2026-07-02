"""
Agent 专用 Pydantic 数据模型（模块二）
"""
from typing import List, Optional, Literal, Any, Dict
from pydantic import BaseModel, Field


# ============ 任务相关模型 ============

TaskType = Literal["data_query", "calculate", "chart", "analyze", "compare"]


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


# ============ 分析模板模型 ============

class TemplateInfo(BaseModel):
    """分析模板信息"""
    name: str = Field(..., description="模板标识（英文）")
    display_name: str = Field(..., description="模板展示名（中文）")
    description: str = Field(..., description="模板说明")
    category: str = Field(..., description="模板分类")


# ============ API 请求/响应模型（与 models/schemas.py 共享）============

class AgentRequest(BaseModel):
    """Agent 分析请求"""
    query: str = Field(..., description="用户分析需求", min_length=1)
    session_id: str = Field(default="default", description="会话 ID")
    template: Optional[str] = Field(default=None, description="预设模板名称")


class AgentResponse(BaseModel):
    """Agent 分析响应"""
    report: str = Field(default="", description="Markdown 报告")
    charts: List[str] = Field(default_factory=list, description="图表 base64 列表")
    processing_time: float = Field(default=0.0, description="总耗时（秒）")
    task_count: int = Field(default=0, description="执行子任务数")


class ClarifyRequest(BaseModel):
    """追问回复请求"""
    query: str = Field(..., description="用户对追问的回答")
    session_id: str = Field(default="default")
