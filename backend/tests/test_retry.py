"""
错误恢复与重试机制单元测试

覆盖：
- @retry 指数退避重试（成功/失败/部分失败）
- 熔断器状态机（CLOSED→OPEN→HALF_OPEN→CLOSED）
- CircuitBreakerOpenError 快速失败
- llm_retry 预配置实例
"""
import time
import pytest
from utils.retry import (
    retry,
    CircuitBreaker,
    CircuitBreakerOpenError,
    circuit_breaker,
    llm_retry,
)


# ==================== retry 装饰器测试 ====================

class TestRetrySuccess:
    """retry 装饰器 — 成功场景"""

    def test_first_attempt_succeeds(self):
        call_count = [0]

        @retry(max_retries=3, base_delay=0.01)
        def succeed_first_time():
            call_count[0] += 1
            return "ok"

        result = succeed_first_time()
        assert result == "ok"
        assert call_count[0] == 1

    def test_succeeds_on_second_attempt(self):
        call_count = [0]

        @retry(max_retries=3, base_delay=0.01)
        def succeed_second_time():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("临时错误")
            return "ok"

        result = succeed_second_time()
        assert result == "ok"
        assert call_count[0] == 2

    def test_succeeds_on_last_attempt(self):
        call_count = [0]

        @retry(max_retries=2, base_delay=0.01)
        def succeed_last_time():
            call_count[0] += 1
            if call_count[0] < 3:  # 第1、2次失败，第3次（最后一次重试）成功
                raise ValueError("临时错误")
            return "ok"

        result = succeed_last_time()
        assert result == "ok"
        assert call_count[0] == 3  # 1 initial + 2 retries = 3 total


class TestRetryFailure:
    """retry 装饰器 — 失败场景"""

    def test_all_attempts_fail(self):
        call_count = [0]

        @retry(max_retries=2, base_delay=0.01)
        def always_fails():
            call_count[0] += 1
            raise ValueError("总是失败")

        with pytest.raises(ValueError, match="总是失败"):
            always_fails()

        assert call_count[0] == 3  # 1 initial + 2 retries

    def test_raises_last_exception(self):
        @retry(max_retries=2, base_delay=0.01)
        def fail_with_different_errors():
            if not hasattr(fail_with_different_errors, 'count'):
                fail_with_different_errors.count = 0
            fail_with_different_errors.count += 1
            if fail_with_different_errors.count == 1:
                raise KeyError("第一个错误")
            elif fail_with_different_errors.count == 2:
                raise ValueError("第二个错误")
            else:
                raise RuntimeError("最终错误")

        with pytest.raises(RuntimeError, match="最终错误"):
            fail_with_different_errors()

    def test_non_matching_exception_not_caught(self):
        """只捕获指定异常类型"""
        call_count = [0]

        @retry(max_retries=3, base_delay=0.01, exceptions=(ValueError,))
        def fail_with_type_error():
            call_count[0] += 1
            raise TypeError("类型错误不重试")

        with pytest.raises(TypeError):
            fail_with_type_error()

        assert call_count[0] == 1  # 不重试


class TestRetryTiming:
    """retry 装饰器 — 退避时序"""

    def test_exponential_backoff_timing(self):
        """验证退避延迟大致符合指数增长"""
        delays = []

        @retry(max_retries=3, base_delay=0.05, backoff_factor=2.0)
        def timed_func():
            # 用函数的一个属性来跟踪调用时机，不在函数开头记录时间
            # 因为在重试之间 sleep 了
            pass

        # 改用更直接的方式测试：模拟场景
        call_times = []
        call_count = [0]

        @retry(max_retries=3, base_delay=0.05, backoff_factor=2.0)
        def fail_three_times():
            call_times.append(time.time())
            call_count[0] += 1
            if call_count[0] <= 3:
                raise ValueError("fail")
            return "ok"

        result = fail_three_times()
        assert result == "ok"
        assert call_count[0] == 4  # 3 fails + 1 success

        # 验证重试间隔大致符合：50ms, 100ms, 200ms
        intervals = [call_times[i + 1] - call_times[i] for i in range(3)]
        # 第一次重试延迟 ≈ 50ms
        assert 0.02 < intervals[0] < 0.15, f"第一次延迟 {intervals[0]*1000:.0f}ms 不在预期范围"
        # 第二次重试延迟 ≈ 100ms
        assert 0.05 < intervals[1] < 0.20, f"第二次延迟 {intervals[1]*1000:.0f}ms 不在预期范围"
        # 第三次重试延迟 ≈ 200ms
        assert 0.10 < intervals[2] < 0.35, f"第三次延迟 {intervals[2]*1000:.0f}ms 不在预期范围"


class TestRetryPreservesSignature:
    """retry 装饰器保留函数签名"""

    def test_preserves_name_and_docstring(self):
        @retry(max_retries=2)
        def my_test_func(x, y=1):
            """测试文档字符串"""
            return x + y

        assert my_test_func.__name__ == "my_test_func"
        assert "测试文档字符串" in my_test_func.__doc__

    def test_preserves_arguments(self):
        @retry(max_retries=2, base_delay=0.01)
        def add(a, b, c=0):
            return a + b + c

        assert add(1, 2) == 3
        assert add(1, 2, c=3) == 6
        assert add(a=1, b=2) == 3


# ==================== 熔断器测试 ====================

class TestCircuitBreakerStateMachine:
    """熔断器状态机"""

    def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        assert cb.state == "closed"
        assert cb.failure_count == 0

    def test_closed_to_open(self):
        """连续失败达到阈值 → 熔断"""
        call_count = [0]

        @CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=60)
        def always_fails():
            call_count[0] += 1
            raise ValueError("fail")

        cb = always_fails.circuit_breaker

        # 前 3 次失败，电路仍闭合
        for _ in range(3):
            with pytest.raises(ValueError):
                always_fails()

        assert cb.failure_count == 3

        # 第 4 次应该抛 CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError, match="电路断开"):
            always_fails()

        assert cb.state == "open"
        assert call_count[0] == 3  # 第 4 次根本没调用

    def test_half_open_success(self):
        """半开探测成功 → 闭合"""
        call_count = [0]

        # 短冷却时间方便测试
        @CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=0.1)
        def succeed_after_cooldown():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ValueError("fail")
            return "ok"

        cb = succeed_after_cooldown.circuit_breaker

        # 两次失败 → 熔断
        for _ in range(2):
            with pytest.raises(ValueError):
                succeed_after_cooldown()

        assert cb.state == "open"

        # 等待冷却
        time.sleep(0.15)

        # 半开探测 → 成功 → 闭合
        result = succeed_after_cooldown()
        assert result == "ok"
        assert cb.state == "closed"
        assert cb.failure_count == 0

    def test_half_open_failure(self):
        """半开探测失败 → 重新熔断"""
        call_count = [0]

        @CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=0.1)
        def fails_even_after_cooldown():
            call_count[0] += 1
            raise ValueError("永远失败")

        cb = fails_even_after_cooldown.circuit_breaker

        # 两次失败 → 熔断
        for _ in range(2):
            with pytest.raises(ValueError):
                fails_even_after_cooldown()
        assert cb.state == "open"

        time.sleep(0.15)

        # 半开探测 → 失败 → 重新熔断
        with pytest.raises(ValueError):
            fails_even_after_cooldown()
        assert cb.state == "open"  # 重新熔断

    def test_reset_circuit_breaker(self):
        """手动重置"""
        cb = CircuitBreaker(name="test", failure_threshold=2, cooldown_seconds=60)

        @cb
        def fails():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                fails()

        assert cb.state == "open"

        cb.reset()
        assert cb.state == "closed"
        assert cb.failure_count == 0

    def test_success_resets_failure_count(self):
        """成功调用重置失败计数"""
        call_count = [0]

        @CircuitBreaker(name="test", failure_threshold=5)
        def sometimes_fails():
            call_count[0] += 1
            if call_count[0] % 2 == 1:
                raise ValueError("fail")
            return "ok"

        cb = sometimes_fails.circuit_breaker

        # 失败交替出现（永远不会达到 threshold=5）
        for i in range(10):
            if i % 2 == 0:
                with pytest.raises(ValueError):
                    sometimes_fails()
            else:
                assert sometimes_fails() == "ok"

        assert cb.state == "closed"
        assert cb.failure_count == 0  # 成功调用后重置


class TestCircuitBreakerDecorator:
    """@circuit_breaker 便捷装饰器"""

    def test_convenience_decorator(self):
        call_count = [0]

        @circuit_breaker(failure_threshold=2, cooldown_seconds=60)
        def my_func():
            call_count[0] += 1
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                my_func()

        with pytest.raises(CircuitBreakerOpenError):
            my_func()

        assert call_count[0] == 2


class TestLLMRetry:
    """llm_retry 预配置装饰器"""

    def test_llm_retry_basic(self):
        call_count = [0]

        @llm_retry(max_retries=2, base_delay=0.01)
        def mock_llm():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("网络超时")
            return "response"

        result = mock_llm()
        assert result == "response"
        assert call_count[0] == 3

    def test_llm_retry_exhausted(self):
        @llm_retry(max_retries=2, base_delay=0.01)
        def mock_llm_fail():
            raise ConnectionError("一直超时")

        with pytest.raises(ConnectionError):
            mock_llm_fail()

    def test_llm_retry_handles_429(self):
        """429 限流时额外等待（不抛异常）"""
        call_count = [0]

        @llm_retry(max_retries=2, base_delay=0.01)
        def mock_429():
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("429 Too Many Requests")
            return "ok"

        result = mock_429()
        assert result == "ok"
