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
    version="0.3.0",
)

# CORS 配置（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    logger.info("启动智能财务分析平台...")
    uvicorn.run(app, host="0.0.0.0", port=8001)
