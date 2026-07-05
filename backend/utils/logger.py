"""
结构化日志系统 — trace_id + JSON 文件 + 控制台 + 按天轮转

特性：
1. trace_id 贯穿全链路（logger.configure(patcher=...) 全局注入，零侵入）
2. 双通道输出：控制台（彩色可读）+ 文件（JSON，按天轮转，保留7天）
3. TraceTimer：关键节点耗时统计（Planner/Executor/Reporter）
4. trace_id 在 JSON 日志中为独立字段（record.extra.trace_id），可结构化查询

使用方式：
    from utils.logger import setup_logging, set_trace_id, TraceTimer

    setup_logging()                       # 启动时调用一次
    set_trace_id("req_abc123")           # 每个请求开始
    with TraceTimer("planner"): ...      # 计时关键节点
"""

import sys
import time
import uuid
import contextvars
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Generator
from loguru import logger


# ==================== trace_id 上下文变量 ====================

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="-"
)


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """
    设置当前请求的 trace_id。
    不传则自动生成 8 位短 UUID，返回设置后的 trace_id。
    """
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:8]
    _trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> str:
    """获取当前请求的 trace_id"""
    return _trace_id_var.get()


def _inject_trace_id(record: dict):
    """
    loguru 全局 patcher：每条日志写入前，将当前 trace_id 注入 record["extra"]。

    通过 logger.configure(patcher=...) 注册，对所有 handler 生效。
    零侵入——现有 logger.info() 调用无需任何修改，自动带 trace_id。
    """
    record["extra"]["trace_id"] = _trace_id_var.get()


# ==================== 日志初始化 ====================

def setup_logging(
    log_dir: str = "logs",
    level: str = "INFO",
    file_level: str = "DEBUG",
    retention: str = "7 days",
    rotation: str = "00:00",
):
    """
    配置 loguru 全局日志（启动时调用一次）。

    双通道：
    - 控制台：彩色 + trace_id，人类可读
    - 文件：JSON 序列化 + trace_id 独立字段 + 按天轮转 + gz 压缩
    """
    logger.remove()

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # ── 控制台：彩色可读 ──
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[trace_id]}</cyan> | "
            "<level>{message}</level>"
        ),
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # ── 文件：JSON，按天轮转 ──
    logger.add(
        str(log_path / "app_{time:YYYY-MM-DD}.log"),
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level} | "
            "{extra[trace_id]} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        level=file_level,
        rotation=rotation,
        retention=retention,
        compression="gz",
        serialize=True,
        enqueue=True,
        backtrace=True,
        diagnose=False,
        encoding="utf-8",
    )

    # ── 全局 patcher：每条日志自动注入 trace_id ──
    logger.configure(patcher=_inject_trace_id)

    logger.info(f"[日志] 初始化完成: 控制台={level}, 文件={file_level}, "
                f"目录={log_path.resolve()}, 保留={retention}")


# ==================== 计时工具 ====================

@contextmanager
def TraceTimer(name: str, log_level: str = "INFO") -> Generator[None, None, None]:
    """
    关键节点耗时计时。

    用法:
        with TraceTimer("planner"):
            plan = planner.plan(user_input)
        # → [计时] planner 耗时 2.34s
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        log_func = getattr(logger, log_level.lower(), logger.info)
        log_func(f"[计时] {name} 耗时 {elapsed:.2f}s")


def timer_decorator(name: str = None):
    """计时装饰器（备用）"""
    def decorator(func):
        import functools
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            label = name or func.__name__
            with TraceTimer(label):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# ==================== 请求级日志上下文 ====================

@contextmanager
def RequestLogContext(trace_id: Optional[str] = None, user_input: str = ""):
    """
    请求级日志上下文。

    用法:
        with RequestLogContext(user_input="分析茅台ROE"):
            planner_node(state)
            executor_node(state)
            reporter_node(state)
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
