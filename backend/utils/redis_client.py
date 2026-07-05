"""
Redis 集成 — 会话存储 + 分布式限流

当 REDIS_URL 环境变量设置时自动启用 Redis，否则回退内存实现。
设计为 drop-in replacement：外部 API 不变，内部根据配置切换后端。

使用:
    from utils.redis_client import get_redis, RateLimiter, SessionStore
    r = get_redis()          # redis.Redis 或 None
    limiter = RateLimiter()  # 自动选择 Redis/内存
    store = SessionStore()   # 自动选择 Redis/内存
"""

import os
import time
import threading
from collections import defaultdict
from typing import Optional, List, Dict, Any
from loguru import logger

REDIS_URL = os.getenv("REDIS_URL", "")

_redis_client = None
_redis_available = False


def get_redis():
    """获取 Redis 客户端（不可用时返回 None）"""
    global _redis_client, _redis_available
    if _redis_client is None and REDIS_URL:
        try:
            import redis
            _redis_client = redis.Redis.from_url(
                REDIS_URL, socket_connect_timeout=3, socket_timeout=3, decode_responses=True
            )
            _redis_client.ping()
            _redis_available = True
            logger.info(f"[Redis] 已连接: {REDIS_URL}")
        except Exception as e:
            logger.warning(f"[Redis] 不可用({e})，回退内存实现")
            _redis_client = None
            _redis_available = False
    return _redis_client if _redis_available else None


# ==================== 限流器（Redis/内存 双模式） ====================

class RateLimiter:
    """
    滑动窗口限流器 — Redis 优先，内存回退。

    用法:
        limiter = RateLimiter()
        allowed, retry_after = limiter.is_allowed(ip, "chat", limit=10)
    """

    def __init__(self, window_seconds: int = 60):
        self._window = window_seconds
        self._memory_store: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int) -> tuple:
        """
        检查请求是否在限流范围内。

        返回: (allowed: bool, retry_after_seconds: int)
        """
        r = get_redis()
        if r:
            return self._redis_check(r, key, limit)
        return self._memory_check(key, limit)

    def _redis_check(self, r, key: str, limit: int) -> tuple:
        """Redis 滑动窗口（sorted set）"""
        now = time.time()
        cutoff = now - self._window
        rkey = f"ratelimit:{key}"

        # 原子操作：清理过期 + 计数 + 添加
        pipe = r.pipeline()
        pipe.zremrangebyscore(rkey, 0, cutoff)  # 清理旧记录
        pipe.zcard(rkey)                          # 当前计数
        pipe.zadd(rkey, {str(now): now})          # 添加当前请求
        pipe.expire(rkey, self._window + 10)      # TTL
        _, count, _, _ = pipe.execute()

        if count > limit:
            # 超限：移除刚添加的记录
            r.zrem(rkey, str(now))
            oldest = r.zrange(rkey, 0, 0, withscores=True)
            retry_after = max(int(oldest[0][1] + self._window - now) + 1, 1) if oldest else self._window
            return False, retry_after

        return True, 0

    def _memory_check(self, key: str, limit: int) -> tuple:
        """内存滑动窗口（回退用）"""
        with self._lock:
            now = time.time()
            cutoff = now - self._window
            # 清理过期
            self._memory_store[key] = [t for t in self._memory_store[key] if t > cutoff]

            if len(self._memory_store[key]) >= limit:
                oldest = min(self._memory_store[key])
                retry_after = max(int(oldest + self._window - now) + 1, 1)
                return False, retry_after

            self._memory_store[key].append(now)
            return True, 0

    def reset(self):
        """清空限流记录（测试用）"""
        r = get_redis()
        if r:
            for key in r.keys("ratelimit:*"):
                r.delete(key)
        with self._lock:
            self._memory_store.clear()


# ==================== 会话存储（Redis/内存 双模式） ====================

class SessionStore:
    """
    会话存储 — Redis 优先，内存回退。

    用于存储对话历史、Agent 状态等。
    """

    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
        self._memory_store: Dict[str, List[Dict]] = defaultdict(list)
        self._lock = threading.Lock()

    def get_history(self, session_id: str) -> List[Dict]:
        """获取对话历史"""
        r = get_redis()
        if r:
            import json
            data = r.get(f"session:{session_id}")
            return json.loads(data) if data else []
        with self._lock:
            return list(self._memory_store.get(session_id, []))

    def add_message(self, session_id: str, role: str, content: str):
        """添加一条消息"""
        r = get_redis()
        if r:
            import json
            key = f"session:{session_id}"
            history = self.get_history(session_id)
            history.append({"role": role, "content": content})
            # 只保留最近 20 条
            if len(history) > 20:
                history = history[-20:]
            r.setex(key, self._ttl, json.dumps(history, ensure_ascii=False))
            return
        with self._lock:
            self._memory_store[session_id].append({"role": role, "content": content})
            if len(self._memory_store[session_id]) > 20:
                self._memory_store[session_id] = self._memory_store[session_id][-20:]

    def clear(self, session_id: str):
        """清除会话"""
        r = get_redis()
        if r:
            r.delete(f"session:{session_id}")
            return
        with self._lock:
            self._memory_store.pop(session_id, None)


# 全局实例
_limiter = RateLimiter()
_session_store = SessionStore()


def get_limiter() -> RateLimiter:
    return _limiter


def get_session_store() -> SessionStore:
    return _session_store
