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


class ChatResponse(BaseModel):
    """聊天响应"""
    answer: str
    sources: List[SourceChunk] = []
    processing_time: float = 0.0  # 秒


class DocumentInfo(BaseModel):
    """已上传文档信息"""
    filename: str
    chunk_count: int
    upload_time: str


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: List[DocumentInfo]
    total: int
