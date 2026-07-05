"""
结构化日志系统 — trace_id + JSON 文件 + 控制台 + 按天轮转

特性：
1. trace_id 贯穿全链路（通过 contextvars，format callable 实时读取）
2. 双通道输出：控制台（彩色可读）+ 文件（JSON，按天轮转，保留7天）
3. TraceTimer：关键节点耗时统计（Planner/Executor/Reporter）
4. 与项目已有的 loguru 调用完全兼容，无需逐行改造

使用方式：
    from utils.logger import setup_logging, set_trace_id, TraceTimer

    # 启动时调用一次
    setup_logging()

    # 每个请求开始时设置 trace_id
    set_trace_id("req_abc123")

    # 计时关键节点
    with TraceTimer("planner"):
        plan = planner.plan(user_input)
    # → 自动输出: [计时] planner 耗时 2.3s
"""

import sys
import time
import uuid
import contextvars
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Generator
from loguru import logger


# ==================== trace_id 上下文变量（零侵入） ====================

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="-"
)


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """
    设置当前请求的 trace_id。

    参数:
        trace_id: 可选，不传则自动生成 8 位短 UUID

    返回:
        设置后的 trace_id 字符串
    """
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:8]
    _trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> str:
    """获取当前请求的 trace_id"""
    return _trace_id_var.get()


# ==================== 日志初始化 ====================

def _console_format(record: dict) -> str:
    """控制台日志格式（含实时 trace_id），彩色标记由 loguru 的 colorize 处理"""
    tid = _trace_id_var.get()
    # 保留原始 colorize 标记
    return (
        "<green>{time:HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        f"<cyan>{tid}</cyan> | "
        "<level>{message}</level>\n"
        "{exception}"
    )


def _file_format(record: dict) -> str:
    """文件日志格式（含实时 trace_id）"""
    tid = _trace_id_var.get()
    return (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level} | "
        f"{tid} | "
        "{name}:{function}:{line} | "
        "{message}\n"
        "{exception}"
    )


def setup_logging(
    log_dir: str = "logs",
    level: str = "INFO",
    file_level: str = "DEBUG",
    retention: str = "7 days",
    rotation: str = "00:00",
):
    """
    配置 loguru 全局日志。

    参数:
        log_dir: 日志文件目录
        level: 控制台最低日志级别
        file_level: 文件最低日志级别
        retention: 日志保留时间（loguru 格式，如 "7 days"）
        rotation: 日志轮转策略（"00:00" = 每天午夜）

    调用时机：应用启动时调用一次。

    双通道输出：
    - 控制台：彩色格式，人类可读，包含 trace_id
    - 文件：JSON 格式，结构化，按天轮转 + gz 压缩
    """
    # 移除默认 handler
    logger.remove()

    # 确保日志目录存在
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # ── 控制台通道：彩色可读 ──
    logger.add(
        sys.stderr,
        format=_console_format,
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # ── 文件通道：JSON 格式，按天轮转 ──
    logger.add(
        str(log_path / "app_{time:YYYY-MM-DD}.log"),
        format=_file_format,
        level=file_level,
        rotation=rotation,
        retention=retention,
        compression="gz",
        serialize=True,       # JSON 格式
        enqueue=True,         # 多进程安全
        backtrace=True,
        diagnose=False,       # 文件不输出变量诊断（减少体积）
        encoding="utf-8",
    )

    logger.info(f"[日志] 初始化完成: 控制台={level}, 文件={file_level}, "
                f"目录={log_path.resolve()}, 保留={retention}")


# ==================== 计时工具 ====================

@contextmanager
def TraceTimer(name: str, log_level: str = "INFO") -> Generator[None, None, None]:
    """
    关键节点耗时计时的上下文管理器。

    用法:
        with TraceTimer("planner"):
            plan = planner.plan(user_input)
        # 退出时自动输出: [计时] planner 耗时 2.34s

    参数:
        name: 节点名称（planner / executor / reporter 等）
        log_level: 日志级别，默认 INFO
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        log_func = getattr(logger, log_level.lower(), logger.info)
        log_func(f"[计时] {name} 耗时 {elapsed:.2f}s")


def timer_decorator(name: str = None):
    """
    计时装饰器（备用方案）。

    用法:
        @timer_decorator("planner_node")
        def planner_node(state):
            ...
    """
    def decorator(func):
        import functools
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            label = name or func.__name__
            with TraceTimer(label):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# ==================== 请求级别的日志上下文 ====================

@contextmanager
def RequestLogContext(trace_id: Optional[str] = None, user_input: str = ""):
    """
    请求级日志上下文管理器。

    用法:
        with RequestLogContext(user_input="分析茅台ROE"):
            # 此范围内的所有 logger 调用自动带 trace_id
            planner_node(state)
            executor_node(state)
            reporter_node(state)

    参数:
        trace_id: 可选，不传自动生成
        user_input: 用户输入（用于日志开头）
    """
    tid = set_trace_id(trace_id)
    start = time.perf_counter()
    logger.info(f"[请求开始] trace_id={tid}, query={user_input[:80]}")
    try:
        yield tid
    except Exception as e:
        logger.error(f"[请求异常] trace_id={tid}, error={e}")
        raise
    finally:
        elapsed = time.perf_counter() - start
        logger.info(f"[请求结束] trace_id={tid}, 总耗时={elapsed:.2f}s")
