"""
API 安全中间件 — 鉴权 + 限流

鉴权：基于 X-API-Key Header 的简单 Token 鉴权
限流：Redis 滑动窗口优先 + 内存回退，按 IP + 接口类型分别计数

设计要点：
- /health /docs /openapi.json 等公开路径不鉴权不限流
- API_KEY 为空时自动生成开发密钥（V8.1：不再零鉴权对外开放）
- RATE_LIMIT_ENABLED=false = 关闭限流
- chat/stream 接口单独限制（LLM 调用成本高，默认 10/min）
- 通用接口默认 30/min
- REDIS_URL 设置时自动切换 Redis 后端（分布式安全）
"""
import secrets
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

import config
from utils.redis_client import get_limiter

# ============ 公开路径 ============

PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


def _is_public_path(path: str) -> bool:
    """判断是否为公开路径（不鉴权、不限流）"""
    if path in PUBLIC_PATHS:
        return True
    if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi"):
        return True
    return False


def _is_chat_endpoint(path: str) -> bool:
    """判断是否为 LLM 调用接口（chat/stream），需要更严格的限流"""
    return "/chat" in path or "/stream" in path


def _get_client_ip(request: Request) -> str:
    """获取客户端真实 IP（优先 X-Forwarded-For）"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# ============ V8.1: 开发密钥（API_KEY 为空时自动生成）============

_dev_api_key: str = ""  # 模块级内部变量，不污染 config.API_KEY


def _get_effective_key() -> str:
    """获取当前生效的 API Key：配置值优先，否则回退到自动生成的开发密钥"""
    return config.API_KEY or _dev_api_key


# ============ 中间件 ============


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    安全中间件：鉴权 + 限流一体

    执行顺序：
    1. 公开路径检查 → 直接放行
    2. 鉴权检查（有效 API Key 非空时，V8.1 含自动生成的开发密钥）
    3. 限流检查（RATE_LIMIT_ENABLED 时）

    注意：config 通过 import config 模块引用，运行时读取，
    测试中可以通过修改 config.API_KEY 等方式切换行为。
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client_ip = _get_client_ip(request)

        # ---- 公开路径：完全不拦截 ----
        if _is_public_path(path):
            return await call_next(request)

        # ---- 鉴权（V8.1：有效 Key = config.API_KEY 或自动生成的开发密钥）----
        effective_key = _get_effective_key()
        if effective_key:
            client_key = request.headers.get("X-API-Key", "")
            if client_key != effective_key:
                logger.warning(
                    f"鉴权失败: {request.method} {path} (IP: {client_ip})"
                )
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "未授权：缺少有效的 API Key，请在请求头中设置 X-API-Key"
                    },
                )

        # ---- 限流（运行时读取 config）----
        if config.RATE_LIMIT_ENABLED:
            if _is_chat_endpoint(path):
                limit = config.RATE_LIMIT_CHAT_PER_MINUTE
                category = "chat"
            else:
                limit = config.RATE_LIMIT_PER_MINUTE
                category = "api"

            allowed, retry_after = get_limiter().is_allowed(f"{client_ip}:{category}", limit)
            if not allowed:
                logger.warning(
                    f"限流触发: {client_ip} → {path} ({category}, {limit}/min)"
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": f"请求过于频繁，请 {retry_after} 秒后重试（{category} 限制 {limit}/分钟）"
                    },
                    headers={"Retry-After": str(retry_after)},
                )

        return await call_next(request)


# ============ 安装入口 ============


def setup_auth_middleware(app: FastAPI):
    """
    为 FastAPI 应用安装安全中间件（鉴权 + 限流）

    调用时机：app 创建之后、路由注册之后

    V8.1 安全加固：API_KEY 为空时自动生成开发密钥，不再零鉴权对外开放。
    开发密钥在启动时打印到控制台，前端需在请求头中携带 X-API-Key。
    """
    global _dev_api_key

    # V8.1: 开发模式下自动生成密钥，杜绝零鉴权
    if not config.API_KEY:
        _dev_api_key = "dev-" + secrets.token_hex(16)
        logger.warning("=" * 60)
        logger.warning("⚠ 安全提示：未配置 API_KEY，已自动生成开发密钥")
        logger.warning(f"   开发密钥: {_dev_api_key}")
        logger.warning("   请在请求头中设置 X-API-Key 使用，或配置 API_KEY 环境变量")
        logger.warning("=" * 60)

    app.add_middleware(SecurityMiddleware)

    msgs = []
    effective = _get_effective_key()
    if effective:
        if effective.startswith("dev-"):
            msgs.append(f"API Key 鉴权已启用（开发密钥: {effective[:10]}...）")
        else:
            msgs.append("API Key 鉴权已启用")
    else:
        msgs.append("API Key 鉴权未配置（开发模式）")

    if config.RATE_LIMIT_ENABLED:
        msgs.append(
            f"限流已启用（通用 {config.RATE_LIMIT_PER_MINUTE}/min，Chat {config.RATE_LIMIT_CHAT_PER_MINUTE}/min）"
        )
    else:
        msgs.append("限流已关闭")

    logger.info(" | ".join(msgs))
