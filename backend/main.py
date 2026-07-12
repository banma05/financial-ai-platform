"""
智能财务分析平台 - FastAPI 入口
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from db import init_db
from api.rag import router as rag_router
from api.agent import router as agent_router

# ── V8.0: 财务数据模型（必须先导入再 init_db，确保表被创建）──
import db.financial_models  # noqa: F401

# 初始化业务数据库（SQLite → 生产切 MySQL）
init_db()

app = FastAPI(
    title="智能财务分析平台",
    description="智能财务分析平台 — 三模块架构：知识库 + Agent + MCP",
    version="0.4.0",
)

# CORS 配置（前端跨域访问）
# 生产环境应通过 CORS_ORIGINS 环境变量指定具体域名（如 "http://localhost:8501,https://app.example.com"）
# 开发环境默认允许本地 Streamlit（8501）和 localhost
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:8501,http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求追踪中间件（可观测性）
from fastapi import Request
import time as _time


@app.middleware("http")
async def monitor_middleware(request: Request, call_next):
    start = _time.perf_counter()
    response = None
    success = True
    try:
        response = await call_next(request)
    except Exception:
        success = False
        raise
    finally:
        elapsed_ms = (_time.perf_counter() - start) * 1000
        from utils.monitor import get_tracker
        endpoint = request.url.path.rsplit("/", 1)[0] if "/" in request.url.path else request.url.path
        get_tracker().record(endpoint, elapsed_ms, success)
    return response

# 注册路由
app.include_router(rag_router)
app.include_router(agent_router)

# 安装安全中间件（鉴权 + 限流）
from middleware.auth import setup_auth_middleware
setup_auth_middleware(app)


@app.get("/")
async def root():
    return {
        "message": "智能财务分析平台 API",
        "version": "0.4.0",
        "docs": "/docs",
    }


# ── 管理 API（知识库管理 + 可观测性）──

@app.get("/api/v1/admin/health")
async def admin_health():
    """系统健康检查"""
    from utils.monitor import get_health_status
    return get_health_status()


@app.get("/api/v1/admin/stats/monitor")
async def admin_monitor_stats():
    """请求统计（延迟/成功率/端点分布）"""
    from utils.monitor import get_tracker, check_alerts
    tracker = get_tracker()
    return {
        **tracker.get_stats(),
        "alerts": check_alerts(),
    }


@app.get("/api/v1/admin/stats/corpus")
async def admin_corpus_stats():
    """知识库统计"""
    from rag.corpus_manager import get_corpus_stats
    return get_corpus_stats()


@app.get("/api/v1/admin/corpus/validate")
async def admin_corpus_validate():
    """知识库质量检查"""
    from rag.corpus_manager import validate_documents
    return validate_documents()


@app.get("/api/v1/admin/corpus/changes")
async def admin_corpus_changes():
    """检测新增/修改文档"""
    from rag.corpus_manager import check_new_documents
    return check_new_documents()


@app.post("/api/v1/admin/corpus/snapshot")
async def admin_corpus_snapshot(label: str = ""):
    """保存知识库版本快照"""
    from rag.corpus_manager import save_snapshot
    return save_snapshot(label)


@app.get("/api/v1/admin/corpus/snapshots")
async def admin_corpus_snapshots():
    """列出所有版本快照"""
    from rag.corpus_manager import list_snapshots
    return {"snapshots": list_snapshots()}


@app.get("/api/v1/admin/stats/cost")
async def admin_cost_stats():
    """Token 用量和费用统计（V6.0 新增）"""
    from db import SessionLocal, TokenUsageLog
    from sqlalchemy import func
    db = SessionLocal()
    try:
        total_tokens = db.query(func.sum(TokenUsageLog.total_tokens)).scalar() or 0
        total_cost = db.query(func.sum(TokenUsageLog.estimated_cost)).scalar() or 0
        total_calls = db.query(func.count(TokenUsageLog.id)).scalar() or 0
        # 按模型分组
        rows = db.query(
            TokenUsageLog.model,
            func.sum(TokenUsageLog.total_tokens),
            func.sum(TokenUsageLog.estimated_cost),
            func.count(TokenUsageLog.id),
        ).group_by(TokenUsageLog.model).all()
        by_model = [
            {"model": m, "tokens": int(t or 0), "cost": round(c or 0, 4), "calls": n}
            for m, t, c, n in rows
        ]
        return {
            "total_tokens": int(total_tokens),
            "total_cost": round(total_cost, 4),
            "total_calls": total_calls,
            "by_model": by_model,
        }
    finally:
        db.close()


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    logger.info("启动智能财务分析平台...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
