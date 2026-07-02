"""
业务数据库模型 — SQLAlchemy ORM

表结构：
  documents     — 上传的文档元数据
  chat_history  — 对话记录（会话内保留）
  query_log     — 查询日志（审计 + 统计分析）
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON
from .database import Base


class Document(Base):
    """已上传的文档元数据"""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(500), nullable=False, comment="原始文件名")
    file_path = Column(String(1000), nullable=False, comment="本地存储路径")
    file_size = Column(Integer, default=0, comment="文件大小（字节）")
    page_count = Column(Integer, default=0, comment="PDF 原始页数")
    chunk_count = Column(Integer, default=0, comment="切分后的文本块数")
    status = Column(String(20), default="active", comment="状态：active / deleted")
    upload_time = Column(DateTime, default=datetime.now, comment="上传时间")

    def to_dict(self):
        return {
            "filename": self.filename,
            "chunk_count": self.chunk_count,
            "page_count": self.page_count,
            "file_size": self.file_size,
            "upload_time": self.upload_time.isoformat() if self.upload_time else "",
        }


class ChatHistory(Base):
    """对话记录 —— 持久化问答，支持历史回溯"""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, default="default", comment="会话ID")
    role = Column(String(20), nullable=False, comment="角色：user / assistant")
    query = Column(Text, default="", comment="用户问题")
    answer = Column(Text, default="", comment="AI 回答")
    sources_json = Column(JSON, default=list, comment="引用来源列表")
    processing_time = Column(Float, default=0.0, comment="处理耗时（秒）")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "query": self.query,
            "answer": self.answer,
            "sources": self.sources_json or [],
            "processing_time": self.processing_time,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


class QueryLog(Base):
    """查询日志 —— 用于审计、用量统计、检索效果分析"""
    __tablename__ = "query_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, default="", comment="用户原始问题")
    processed_query = Column(Text, default="", comment="处理后的查询")
    top_k = Column(Integer, default=5, comment="检索数量")
    chunks_count = Column(Integer, default=0, comment="实际检索到的chunk数")
    processing_time = Column(Float, default=0.0, comment="处理耗时（秒）")
    has_sources = Column(Integer, default=0, comment="是否有检索结果：0=无 1=有")
    created_at = Column(DateTime, default=datetime.now, comment="查询时间")


class AnalysisLog(Base):
    """分析任务日志（模块二 Agent）—— 记录每次分析请求的执行情况"""
    __tablename__ = "analysis_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, default="default", comment="会话ID")
    user_input = Column(Text, default="", comment="用户分析需求")
    template_name = Column(String(100), default="", comment="使用的分析模板")
    task_count = Column(Integer, default=0, comment="子任务数")
    task_details = Column(JSON, default=list, comment="各子任务详情")
    report = Column(Text, default="", comment="生成的报告")
    chart_count = Column(Integer, default=0, comment="生成的图表数")
    processing_time = Column(Float, default=0.0, comment="总处理耗时（秒）")
    status = Column(String(20), default="completed", comment="completed / failed / clarification")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_input": self.user_input,
            "template_name": self.template_name,
            "task_count": self.task_count,
            "chart_count": self.chart_count,
            "processing_time": self.processing_time,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }
