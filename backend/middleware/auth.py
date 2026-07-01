"""
API 安全中间件 — 鉴权 + 限流

鉴权：基于 X-API-Key Header 的简单 Token 鉴权
限流：内存滑动窗口，按 IP + 接口类型分别计数

设计要点：
- /health /docs /openapi.json 等公开路径不鉴权不限流
- API_KEY 为空 = 开发模式，不启用鉴权
- RATE_LIMIT_ENABLED=false = 关闭限流
- chat/stream 接口单独限制（LLM 调用成本高，默认 10/min）
- 通用接口默认 30/min
"""
import time
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

import config

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


# ============ 内存滑动窗口限流器 ============

class RateLimiter:
    """
    基于 IP 的内存滑动窗口限流器

    不持久化，重启清空。适合 MVP 阶段，生产可替换为 Redis 方案。
    """

    def __init__(self):
        # { "ip:category": [timestamp_1, timestamp_2, ...] }
        self._windows: dict = defaultdict(list)
        self._window_seconds = 60  # 1 分钟窗口

    def reset(self):
        """清空所有限流记录（仅用于测试）"""
        self._windows.clear()

    def _clean(self, key: str):
        """清理过期的请求记录"""
        now = time.time()
        cutoff = now - self._window_seconds
        self._windows[key] = [t for t in self._windows[key] if t > cutoff]

    def is_allowed(self, ip: str, category: str, limit: int) -> tuple[bool, int]:
        """
        检查是否允许请求

        返回: (允许?, 剩余秒数)
        """
        key = f"{ip}:{category}"
        self._clean(key)

        count = len(self._windows[key])
        if count >= limit:
            oldest = min(self._windows[key])
            retry_after = int(oldest + self._window_seconds - time.time()) + 1
            return False, max(retry_after, 1)

        self._windows[key].append(time.time())
        return True, 0


# 全局限流器（可在测试中 reset）
_limiter = RateLimiter()


# ============ 中间件 ============


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    安全中间件：鉴权 + 限流一体

    执行顺序：
    1. 公开路径检查 → 直接放行
    2. 鉴权检查（API_KEY 非空时）
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

        # ---- 鉴权（运行时读取 config，支持测试注入）----
        if config.API_KEY:
            client_key = request.headers.get("X-API-Key", "")
            if client_key != config.API_KEY:
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

            allowed, retry_after = _limiter.is_allowed(client_ip, category, limit)
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


# ============ 兼容旧代码的 limiter 导出 ============

limiter = None  # type: ignore


# ============ 安装入口 ============


def setup_auth_middleware(app: FastAPI):
    """
    为 FastAPI 应用安装安全中间件（鉴权 + 限流）

    调用时机：app 创建之后、路由注册之后
    """
    app.add_middleware(SecurityMiddleware)

    msgs = []
    if config.API_KEY:
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
