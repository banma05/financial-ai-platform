"""
错误恢复与重试机制 — 指数退避 + 熔断器

模块提供两个核心装饰器：

1. @retry ― 指数退避重试
   装饰函数在抛出指定异常时自动重试，每次重试前等待递增的时间。
   默认配置：最多 3 次，初始延迟 1s，退避因子 2 → 1s / 2s / 4s。

2. @circuit_breaker ― 熔断器
   连续失败 N 次后"熔断"（快速失败，不再调用原函数），冷却后
   进入半开状态，允许一次探测请求。探测成功→闭合，失败→重新熔断。

使用示例:
    from utils.retry import retry, circuit_breaker

    @retry(max_retries=3, base_delay=1.0, backoff_factor=2.0)
    def call_api(url):
        ...

    @circuit_breaker(failure_threshold=5, cooldown_seconds=60)
    def risky_operation():
        ...
"""

import time
import functools
import threading
from typing import Type, Tuple, Callable, Any
from loguru import logger


# ==================== 指数退避重试 ====================

def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    on_retry: Callable = None,
):
    """
    指数退避重试装饰器。

    参数:
        max_retries: 最大重试次数（不含首次调用）
        base_delay: 首次重试前的等待时间（秒）
        backoff_factor: 退避乘数，每次重试延迟 = base_delay * (backoff_factor ** attempt)
        exceptions: 触发重试的异常类型元组
        on_retry: 可选回调，签名 `on_retry(exception, attempt, max_retries)`

    行为:
        - 首次调用（attempt=0）失败 → 等待 base_delay → 重试 attempt=1
        - attempt=1 失败 → 等待 base_delay * backoff_factor → 重试 attempt=2
        - attempt=2 失败 → 等待 base_delay * backoff_factor^2 → 重试 attempt=3
        - 全部失败 → 抛出最后一次的异常

    示例:
        @retry(max_retries=3, base_delay=1.0, backoff_factor=2.0)
        def chat(messages):
            return client.chat.completions.create(...)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        delay = base_delay * (backoff_factor ** attempt)
                        logger.warning(
                            f"[重试] {func.__name__} 第 {attempt + 1}/{max_retries} 次失败: "
                            f"{type(e).__name__}: {str(e)[:120]}，"
                            f"{delay:.1f}s 后重试..."
                        )
                        if on_retry:
                            try:
                                on_retry(e, attempt + 1, max_retries)
                            except Exception:
                                pass  # 回调不应影响重试流程
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[重试] {func.__name__} 已耗尽 {max_retries} 次重试，"
                            f"最终异常: {type(e).__name__}: {str(e)[:200]}"
                        )

            # 所有重试都已耗尽
            raise last_exception

        return wrapper

    return decorator


# ==================== 熔断器（Circuit Breaker） ====================

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

    使用方式:
        cb = CircuitBreaker(name="llm_api", failure_threshold=5, cooldown_seconds=60)

        @cb
        def risky_call():
            ...

        # 运行时查询状态
        print(cb.state)  # "closed" / "open" / "half_open"
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
        """
        参数:
            name: 熔断器名称（用于日志标识）
            failure_threshold: 连续失败多少次后熔断
            cooldown_seconds: 熔断后冷却时间（秒），之后进入半开
            half_open_max_requests: 半开状态允许的最大探测请求数
        """
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
        """当前状态"""
        with self._lock:
            return self._current_state()

    @property
    def failure_count(self) -> int:
        """当前连续失败次数"""
        with self._lock:
            return self._failure_count

    def _current_state(self) -> str:
        """
        检查是否需要状态迁移（调用方须持有 _lock）。

        规则:
        - OPEN 且冷却到期 → HALF_OPEN
        - 其他 → 保持当前状态
        """
        if self._state == self.OPEN:
            if time.time() - self._opened_at >= self.cooldown_seconds:
                self._state = self.HALF_OPEN
                self._half_open_requests = 0
                logger.info(f"[熔断器:{self.name}] 冷却结束，进入半开状态")
        return self._state

    def _on_success(self):
        """调用成功后重置状态"""
        with self._lock:
            if self._state == self.HALF_OPEN:
                logger.info(f"[熔断器:{self.name}] 半开探测成功，闭合电路")
            self._state = self.CLOSED
            self._failure_count = 0
            self._half_open_requests = 0

    def _on_failure(self):
        """调用失败后更新状态"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == self.HALF_OPEN:
                # 半开探测失败 → 重新熔断
                self._state = self.OPEN
                self._opened_at = time.time()
                logger.warning(
                    f"[熔断器:{self.name}] 半开探测失败，重新熔断 "
                    f"(失败 {self._failure_count} 次)"
                )
            elif self._state == self.CLOSED and self._failure_count >= self.failure_threshold:
                # 连续失败达到阈值 → 熔断
                self._state = self.OPEN
                self._opened_at = time.time()
                logger.warning(
                    f"[熔断器:{self.name}] 连续失败 {self._failure_count} 次，"
                    f"电路断开，冷却 {self.cooldown_seconds}s"
                )

    def __call__(self, func: Callable) -> Callable:
        """
        作为装饰器使用。

        @CircuitBreaker(name="api", failure_threshold=5, cooldown_seconds=60)
        def call_api():
            ...
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            with self._lock:
                state = self._current_state()

                if state == self.OPEN:
                    remaining = self.cooldown_seconds - (time.time() - self._opened_at)
                    raise CircuitBreakerOpenError(
                        f"[熔断器:{self.name}] 电路断开中，"
                        f"{remaining:.0f}s 后恢复。"
                        f"连续失败 {self._failure_count} 次。"
                    )

                if state == self.HALF_OPEN:
                    if self._half_open_requests >= self.half_open_max_requests:
                        raise CircuitBreakerOpenError(
                            f"[熔断器:{self.name}] 半开状态，探测请求已达上限"
                        )
                    self._half_open_requests += 1

            # 释放锁后执行实际调用（避免阻塞其他线程）
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise e

        # 暴露熔断器实例供外部查询
        wrapper.circuit_breaker = self
        return wrapper

    def reset(self):
        """手动重置熔断器到闭合状态（运维/测试用）"""
        with self._lock:
            self._state = self.CLOSED
            self._failure_count = 0
            self._half_open_requests = 0
            logger.info(f"[熔断器:{self.name}] 手动重置 → 闭合")


class CircuitBreakerOpenError(Exception):
    """熔断器断路时抛出的异常"""
    pass


# ==================== 便捷工厂函数 ====================

def circuit_breaker(
    failure_threshold: int = 5,
    cooldown_seconds: float = 60.0,
    name: str = None,
):
    """
    熔断器装饰器的便捷工厂。

    与直接实例化 CircuitBreaker 等价，提供更简洁的语法:

        @circuit_breaker(failure_threshold=5, cooldown_seconds=60)
        def my_func():
            ...

    参数:
        failure_threshold: 连续失败多少次后熔断（默认 5）
        cooldown_seconds: 熔断后冷却时间（默认 60s）
        name: 熔断器名称（默认使用函数名）
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


# ==================== 预配置的装饰器实例 ====================

def llm_retry(max_retries: int = 3, base_delay: float = 1.0):
    """
    LLM API 调用专用重试装饰器。

    配置:
        - 3 次重试，1s/2s/4s 退避
        - 捕获所有异常（网络错误、超时、限流等）
        - 第 3 次重试时使用更长等待（应对 API 限流 429）
    """
    def on_llm_retry(exception, attempt, max_retries):
        # 如果检测到限流（429），延长等待
        err_str = str(exception).lower()
        if "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
            extra_wait = 5.0 * attempt  # 429 时额外等待 5s/10s/15s
            logger.warning(f"[LLM重试] 检测到限流(429)，额外等待 {extra_wait}s")
            time.sleep(extra_wait)

    return retry(
        max_retries=max_retries,
        base_delay=base_delay,
        backoff_factor=2.0,
        exceptions=(Exception,),
        on_retry=on_llm_retry,
    )
