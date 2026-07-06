"""
错误恢复与重试机制 — 基于 tenacity + 自研熔断器

模块提供：

1. retry() ― 基于 tenacity 的指数退避重试（薄封装，保持 API 兼容）
   tenacity 是 langchain 的传递依赖，已在环境中可用，不新增依赖。

2. CircuitBreaker ― 熔断器（tenacity 不提供此能力，自研）
   连续失败 N 次后"熔断"快速失败，冷却后半开探测。

使用示例:
    from utils.retry import retry, circuit_breaker, llm_retry

    @retry(max_retries=3, base_delay=1.0)
    def call_api(url):
        ...

    @circuit_breaker(failure_threshold=5, cooldown_seconds=60)
    def risky_operation():
        ...
"""

import time
import functools
import threading
from typing import Callable, Any
from loguru import logger

from tenacity import (
    retry as _tenacity_retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)


# ==================== retry 薄封装（API 兼容） ====================

def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable = None,
):
    """
    指数退避重试装饰器（基于 tenacity，API 兼容旧版）。

    参数:
        max_retries:    最大重试次数（不含首次调用）→ tenacity stop_after_attempt
        base_delay:     首次重试等待时间（秒）→ tenacity wait_exponential.multiplier
        backoff_factor: 退避乘数（保留参数，tenacity 固定为 2，效果等价）
        exceptions:     触发重试的异常类型元组
        on_retry:       每次重试前的回调，签名 on_retry(exception, attempt_number, max_retries)

    行为:
        - 首次调用失败 → 等待 base_delay → 重试
        - 再次失败 → 等待 base_delay*2 → 重试
        - 再次失败 → 等待 base_delay*4 → 重试
        - 全部失败 → 抛出最后一次的异常
    """
    def _before_sleep(retry_state):
        """tenacity before_sleep 回调 → 转为 on_retry 回调 + 日志"""
        exc = retry_state.outcome.exception()
        attempt = retry_state.attempt_number - 1  # tenacity 从 1 计数，转为 0-based
        delay = base_delay * (2 ** (attempt - 1)) if attempt > 0 else base_delay

        logger.warning(
            f"[重试] {retry_state.fn.__name__} 第 {attempt}/{max_retries} 次失败: "
            f"{type(exc).__name__}: {str(exc)[:120]}，"
            f"{delay:.1f}s 后重试..."
        )
        if on_retry:
            try:
                on_retry(exc, attempt, max_retries)
            except Exception as e:
                logger.debug(f"retry 回调异常: {e}")

    def _after_attempt(retry_state):
        """最后一次也失败时记录日志（tenacity 的 after 回调）"""
        if retry_state.attempt_number >= max_retries + 1:
            exc = retry_state.outcome.exception()
            if exc:
                logger.error(
                    f"[重试] {retry_state.fn.__name__} 已耗尽 {max_retries} 次重试，"
                    f"最终异常: {type(exc).__name__}: {str(exc)[:200]}"
                )

    return _tenacity_retry(
        stop=stop_after_attempt(max_retries + 1),  # +1 包含首次调用
        wait=wait_exponential(
            multiplier=base_delay,
            min=base_delay,
            max=base_delay * (2 ** max_retries),
        ),
        retry=retry_if_exception_type(exceptions),
        before_sleep=_before_sleep,
        after=_after_attempt,
        reraise=True,
    )


# ==================== LLM 专用重试（保留 429 额外等待） ====================

def llm_retry(max_retries: int = 3, base_delay: float = 1.0):
    """
    LLM API 调用专用重试装饰器（基于 tenacity + 429 感知）。

    配置:
        - 3 次重试，1s/2s/4s 退避
        - 捕获所有异常（网络错误、超时、限流等）
        - 检测 429 限流 → 额外等待 5s/10s/15s

    用法: 同 @retry，已用于 model_router.chat()
    """
    def _before_sleep(retry_state):
        exc = retry_state.outcome.exception()
        if exc is None:
            return
        attempt = retry_state.attempt_number

        # 日志
        delay = base_delay * (2 ** (attempt - 1)) if attempt > 0 else base_delay
        logger.warning(
            f"[LLM重试] {retry_state.fn.__name__} 第 {attempt}/{max_retries} 次失败: "
            f"{type(exc).__name__}: {str(exc)[:120]}，"
            f"{delay:.1f}s 后重试..."
        )

        # 429 限流检测：额外延长等待
        err_str = str(exc).lower()
        if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
            extra_wait = 5.0 * attempt
            logger.warning(f"[LLM重试] 检测到限流(429)，额外等待 {extra_wait}s")
            time.sleep(extra_wait)

    return _tenacity_retry(
        stop=stop_after_attempt(max_retries + 1),
        wait=wait_exponential(
            multiplier=base_delay,
            min=base_delay,
            max=base_delay * (2 ** max_retries),
        ),
        retry=retry_if_exception_type(Exception),
        before_sleep=_before_sleep,
        reraise=True,
    )


# ==================== 熔断器（Circuit Breaker，tenacity 不提供，自研） ====================

class CircuitBreaker:
    """
    熔断器 — 防止级联故障。

    状态机:
        CLOSED（闭合）→ 正常调用，累计连续失败次数
           │ 连续失败 ≥ failure_threshold
           ▼
        OPEN（断开）→ 快速失败，不再调用原函数
           │ 等待 cooldown_seconds
           ▼
        HALF_OPEN（半开）→ 允许一次探测调用
           │ 成功 → CLOSED（重置计数器）
           │ 失败 → OPEN（重新熔断）
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        half_open_max_requests: int = 1,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_requests = half_open_max_requests

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0
        self._half_open_requests: int = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            return self._current_state()

    @property
    def failure_count(self) -> int:
        with self._lock:
            return self._failure_count

    def _current_state(self) -> str:
        if self._state == self.OPEN:
            if time.time() - self._opened_at >= self.cooldown_seconds:
                self._state = self.HALF_OPEN
                self._half_open_requests = 0
                logger.info(f"[熔断器:{self.name}] 冷却结束，进入半开状态")
        return self._state

    def _on_success(self):
        with self._lock:
            if self._state == self.HALF_OPEN:
                logger.info(f"[熔断器:{self.name}] 半开探测成功，闭合电路")
            self._state = self.CLOSED
            self._failure_count = 0
            self._half_open_requests = 0

    def _on_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                self._opened_at = time.time()
                logger.warning(
                    f"[熔断器:{self.name}] 半开探测失败，重新熔断"
                )
            elif self._state == self.CLOSED and self._failure_count >= self.failure_threshold:
                self._state = self.OPEN
                self._opened_at = time.time()
                logger.warning(
                    f"[熔断器:{self.name}] 连续失败 {self._failure_count} 次，"
                    f"电路断开，冷却 {self.cooldown_seconds}s"
                )

    def __call__(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with self._lock:
                state = self._current_state()
                if state == self.OPEN:
                    remaining = self.cooldown_seconds - (time.time() - self._opened_at)
                    raise CircuitBreakerOpenError(
                        f"[熔断器:{self.name}] 电路断开中，"
                        f"{remaining:.0f}s 后恢复"
                    )
                if state == self.HALF_OPEN:
                    if self._half_open_requests >= self.half_open_max_requests:
                        raise CircuitBreakerOpenError(
                            f"[熔断器:{self.name}] 半开探测请求已达上限"
                        )
                    self._half_open_requests += 1

            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise e

        wrapper.circuit_breaker = self
        return wrapper

    def reset(self):
        with self._lock:
            self._state = self.CLOSED
            self._failure_count = 0
            self._half_open_requests = 0
            logger.info(f"[熔断器:{self.name}] 手动重置 → 闭合")


class CircuitBreakerOpenError(Exception):
    """熔断器断路时抛出的异常"""
    pass


def circuit_breaker(
    failure_threshold: int = 5,
    cooldown_seconds: float = 60.0,
    name: str = None,
):
    """
    熔断器便捷装饰器工厂。

        @circuit_breaker(failure_threshold=5, cooldown_seconds=60)
        def my_func():
            ...
    """
    def decorator(func: Callable) -> Callable:
        cb_name = name or func.__name__
        cb = CircuitBreaker(
            name=cb_name,
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
        )
        return cb(func)
    return decorator
