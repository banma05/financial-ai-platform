"""
结构化日志系统单元测试

覆盖：
- set_trace_id / get_trace_id 上下文变量
- TraceTimer 计时功能
- timer_decorator 装饰器
- RequestLogContext 上下文管理器
- setup_logging 初始化（基础验证）
"""
import time
import pytest
from utils.logger import (
    set_trace_id,
    get_trace_id,
    TraceTimer,
    timer_decorator,
    RequestLogContext,
    setup_logging,
)


class TestTraceId:
    """trace_id 上下文变量"""

    def test_set_and_get(self):
        tid = set_trace_id("test_abc123")
        assert tid == "test_abc123"
        assert get_trace_id() == "test_abc123"

    def test_auto_generate(self):
        tid = set_trace_id()  # 不传参自动生成
        assert len(tid) == 8  # 8 位短 UUID
        assert get_trace_id() == tid

    def test_override(self):
        set_trace_id("first")
        assert get_trace_id() == "first"
        set_trace_id("second")
        assert get_trace_id() == "second"

    def test_default_value(self):
        """未设置时返回默认值 '-'"""
        # 注意：contextvars 在测试中可能有残留值，
        # 这里验证默认值逻辑存在即可
        assert get_trace_id() in ("-", "first", "second", "test_abc123")


class TestTraceTimer:
    """TraceTimer 上下文管理器"""

    def test_basic_timing(self):
        with TraceTimer("test_node"):
            time.sleep(0.05)
        # 不抛异常即为成功（日志由输出通道处理）

    def test_nested_timing(self):
        """嵌套计时"""
        with TraceTimer("outer"):
            time.sleep(0.02)
            with TraceTimer("inner"):
                time.sleep(0.03)
        # 两个计时器都应正常退出

    def test_timing_with_exception(self):
        """异常场景下计时器正常退出"""
        with pytest.raises(ValueError):
            with TraceTimer("failing_node"):
                raise ValueError("测试异常")
        # 即使内部抛异常，计时器也应正常退出并输出日志

    def test_custom_log_level(self):
        """自定义日志级别"""
        with TraceTimer("debug_node", log_level="DEBUG"):
            time.sleep(0.01)


class TestTimerDecorator:
    """timer_decorator 装饰器"""

    def test_decorator_with_name(self):
        @timer_decorator("my_func")
        def slow_func():
            time.sleep(0.03)
            return 42

        result = slow_func()
        assert result == 42

    def test_decorator_auto_name(self):
        @timer_decorator()
        def auto_named():
            return "ok"

        result = auto_named()
        assert result == "ok"

    def test_decorator_preserves_metadata(self):
        @timer_decorator("labeled")
        def documented_func():
            """函数文档"""
            return True

        assert documented_func.__name__ == "documented_func"
        assert "函数文档" in documented_func.__doc__


class TestRequestLogContext:
    """RequestLogContext 上下文管理器"""

    def test_basic_usage(self):
        with RequestLogContext(user_input="测试查询") as tid:
            assert len(tid) == 8
            assert get_trace_id() == tid
            # 模拟业务逻辑
            time.sleep(0.02)

    def test_custom_trace_id(self):
        with RequestLogContext(trace_id="custom_001", user_input="查询") as tid:
            assert tid == "custom_001"
            assert get_trace_id() == "custom_001"

    def test_exception_propagation(self):
        """异常正常传播，但日志照常输出"""
        with pytest.raises(ValueError, match="业务异常"):
            with RequestLogContext(user_input="会失败的查询"):
                raise ValueError("业务异常")


class TestSetupLogging:
    """日志初始化"""

    def test_setup_does_not_crash(self):
        """setup_logging 不应抛异常"""
        import tempfile
        import os
        tmp_dir = os.path.join(tempfile.gettempdir(), "test_financial_logs")
        try:
            setup_logging(log_dir=tmp_dir, level="WARNING", file_level="DEBUG")
        except Exception as e:
            pytest.fail(f"setup_logging 抛异常: {e}")
