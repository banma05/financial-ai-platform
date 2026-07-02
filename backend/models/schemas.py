"""
数据模型定义
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""
    filename: str
    file_size: int
    chunk_count: int
    message: str


class SourceChunk(BaseModel):
    """引用来源的文本块"""
    content: str
    source: str       # 文件名
    page: int         # 页码
    score: float      # 相似度分数


class ChatRequest(BaseModel):
    """聊天请求"""
    query: str = Field(..., description="用户问题")
    top_k: int = Field(default=5, description="检索文档数")
    session_id: str = Field(default="default", description="会话ID，用于多轮对话")


class ChatResponse(BaseModel):
    """聊天响应"""
    answer: str
    sources: List[SourceChunk] = []
    processing_time: float = 0.0  # 秒


class DocumentInfo(BaseModel):
    """已上传文档信息"""
    filename: str
    chunk_count: int = 0
    page_count: int = 0
    file_size: int = 0
    upload_time: str = ""


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: List[DocumentInfo]
    total: int


class EvalRequest(BaseModel):
    """评测请求"""
    test_set_path: str = Field(default="", description="测试集 JSON 路径，留空则用默认")
    top_k: int = Field(default=5, description="检索文档数")
    use_llm_judge: bool = Field(default=False, description="是否启用 LLM-as-Judge（耗时更长）")


class EvalSummary(BaseModel):
    """评测汇总指标"""
    avg_recall_at_1: float = 0.0
    avg_recall_at_3: float = 0.0
    avg_recall_at_5: float = 0.0
    avg_mrr: float = 0.0
    avg_ndcg_at_5: float = 0.0
    avg_time_s: float = 0.0   # 平均单题响应时间
    num_questions: int = 0
    total_time_s: float = 0.0


class EvalDetail(BaseModel):
    """单题评测详情"""
    question_id: str
    query: str
    category: str
    difficulty: str
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    ndcg_at_5: float
    time_s: float
    chunks_found: int


class EvalGroupStats(BaseModel):
    """分组统计"""
    count: int
    avg_recall_at_5: float
    avg_mrr: float


class EvalReportResponse(BaseModel):
    """评测报告响应"""
    summary: EvalSummary
    by_difficulty: dict = {}
    by_category: dict = {}
    details: List[EvalDetail] = []
    llm_judge_results: Optional[dict] = None


# ============ Agent 模块模型（模块二）============

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
    clarification: Optional[str] = Field(default=None, description="追问内容")


class TemplateInfo(BaseModel):
    """分析模板信息"""
    name: str = Field(..., description="模板标识（英文）")
    display_name: str = Field(..., description="模板展示名（中文）")
    description: str = Field(..., description="模板说明")
    category: str = Field(..., description="模板分类")
