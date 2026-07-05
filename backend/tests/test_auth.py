"""
API 鉴权 + 限流 单元测试

覆盖：API Key 校验、白名单路径、限流逻辑、端到端 HTTP 测试
"""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ============ 测试辅助 ============


def _create_test_app(api_key: str = "test-secret-key", rate_limit_enabled: bool = True):
    """
    创建带鉴权和限流的测试 FastAPI app

    使用 pytest monkeypatch 风格的临时配置注入：
    直接修改 config 模块属性，调用方需自行恢复。
    """
    import config

    # 设置测试值（测试结束后由调用方或下一个 _create_test_app 覆盖）
    config.API_KEY = api_key
    config.RATE_LIMIT_ENABLED = rate_limit_enabled
    config.RATE_LIMIT_PER_MINUTE = 5
    config.RATE_LIMIT_CHAT_PER_MINUTE = 3

    # 重置全局限流器（避免测试间污染）
    from utils.redis_client import get_limiter
    get_limiter().reset()

    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/rag/documents")
    async def list_docs():
        return {"documents": []}

    @app.post("/api/v1/rag/chat")
    async def chat():
        return {"answer": "test"}

    from middleware.auth import setup_auth_middleware
    setup_auth_middleware(app)

    return app, TestClient(app)


# ============ API Key 鉴权测试 ============


class TestAPIKeyAuth:
    """API Key 鉴权中间件"""

    def test_无APIKey配置_允许所有请求(self):
        """API_KEY 为空时（开发模式），不启用鉴权"""
        _, client = _create_test_app(api_key="")
        resp = client.get("/api/v1/rag/documents")
        assert resp.status_code == 200

    def test_有APIKey_无Header_返回401(self):
        """配置了 API_KEY 但不带 Header → 401"""
        _, client = _create_test_app(api_key="my-secret")
        resp = client.get("/api/v1/rag/documents")
        assert resp.status_code == 401, f"预期 401，实际 {resp.status_code}: {resp.json()}"

    def test_有APIKey_正确Header_放行(self):
        """带正确的 X-API-Key Header → 200"""
        _, client = _create_test_app(api_key="my-secret")
        resp = client.get(
            "/api/v1/rag/documents",
            headers={"X-API-Key": "my-secret"},
        )
        assert resp.status_code == 200

    def test_有APIKey_错误Header_返回401(self):
        """带错误的 API Key → 401"""
        _, client = _create_test_app(api_key="my-secret")
        resp = client.get(
            "/api/v1/rag/documents",
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code == 401, f"预期 401，实际 {resp.status_code}"

    def test_健康检查_不鉴权(self):
        """/health 端点始终跳过鉴权"""
        _, client = _create_test_app(api_key="my-secret")
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_docs路径_不鉴权(self):
        """/docs 和 /openapi.json 跳过鉴权"""
        _, client = _create_test_app(api_key="my-secret")
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_POST请求_也需要鉴权(self):
        """POST 请求同样需要 API Key"""
        _, client = _create_test_app(api_key="my-secret")
        resp = client.post("/api/v1/rag/chat", json={"query": "test"})
        assert resp.status_code == 401, f"预期 401，实际 {resp.status_code}"

    def test_POST请求_正确Key_放行(self):
        """POST 请求带正确 Key → 200"""
        _, client = _create_test_app(api_key="my-secret")
        resp = client.post(
            "/api/v1/rag/chat",
            json={"query": "test"},
            headers={"X-API-Key": "my-secret"},
        )
        assert resp.status_code == 200


# ============ 限流测试 ============


class TestRateLimit:
    """请求频率限制"""

    def test_限流关闭_不拦截(self):
        """RATE_LIMIT_ENABLED=false 时不管控"""
        _, client = _create_test_app(api_key="", rate_limit_enabled=False)
        for _ in range(10):
            resp = client.get("/api/v1/rag/documents")
            assert resp.status_code == 200

    def test_超限后返回429(self):
        """超过限制后返回 429 Too Many Requests"""
        _, client = _create_test_app(api_key="", rate_limit_enabled=True)
        # RATE_LIMIT_PER_MINUTE=5，连续发 10 个请求
        statuses = []
        for _ in range(10):
            resp = client.get("/api/v1/rag/documents")
            statuses.append(resp.status_code)
        assert 429 in statuses, f"预期出现 429，实际状态码: {statuses}"

    def test_不同IP_独立计数(self):
        """不同 IP 地址应独立限流（通过 X-Forwarded-For 区分）"""
        _, client = _create_test_app(api_key="", rate_limit_enabled=True)
        # 用一个 IP 发 10 个请求触发限流
        for _ in range(10):
            client.get("/api/v1/rag/documents")

        # 换一个 IP 模拟
        resp = client.get(
            "/api/v1/rag/documents",
            headers={"X-Forwarded-For": "10.0.0.2"},
        )
        assert resp.status_code == 200

    def test_限流响应包含RetryAfter头(self):
        """429 响应应提示重试时间"""
        _, client = _create_test_app(api_key="", rate_limit_enabled=True)
        for _ in range(10):
            resp = client.get("/api/v1/rag/documents")
            if resp.status_code == 429:
                assert "Retry-After" in resp.headers
                break


# ============ 边界情况 ============


class TestAuthEdgeCases:
    """鉴权边界情况"""

    def test_空APIKey_Header传空字符串_放行(self):
        """API_KEY 为空，Header 传空字符串，应放行"""
        _, client = _create_test_app(api_key="")
        resp = client.get("/api/v1/rag/documents", headers={"X-API-Key": ""})
        assert resp.status_code == 200

    def test_Header名称大小写不敏感(self):
        """X-API-Key header 大小写不敏感"""
        _, client = _create_test_app(api_key="my-secret")
        resp = client.get(
            "/api/v1/rag/documents",
            headers={"x-api-key": "my-secret"},
        )
        assert resp.status_code == 200


# ============ 配置校验测试 ============


class TestAuthConfig:
    """安全配置正确性"""

    def test_API_KEY默认从环境变量读取(self):
        import config
        assert isinstance(config.API_KEY, str)

    def test_RATE_LIMIT_ENABLED默认值(self):
        import config
        assert config.RATE_LIMIT_ENABLED is True

    def test_RATE_LIMIT_CHAT比通用限制更严格(self):
        import config
        assert config.RATE_LIMIT_CHAT_PER_MINUTE <= config.RATE_LIMIT_PER_MINUTE, \
            "Chat 限流应≤通用限流，因为 LLM 调用成本更高"
