"""
智能财务分析平台 - FastAPI 入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from db import init_db
from api.rag import router as rag_router
from api.agent import router as agent_router

# 初始化业务数据库（SQLite → 生产切 MySQL）
init_db()

app = FastAPI(
    title="智能财务分析平台",
    description="智能财务分析平台 — 三模块架构：知识库 + Agent + MCP",
    version="0.4.0",
)

# CORS 配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    logger.info("启动智能财务分析平台...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
