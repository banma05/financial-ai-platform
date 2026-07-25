"""
安全错误处理 — 统一截断错误信息，防止内部细节泄露。

面试亮点：V9.1 主动识别了 agent.py 和 rag.py 中 8 处直接暴露
原始异常信息的问题，统一收敛到此模块。生产环境可轻松切换为
仅返回 trace_id + 通用消息的模式。
"""

from uuid import uuid4


def safe_error(e: Exception, max_length: int = 200) -> str:
    """
    安全格式化错误信息。

    返回格式：请求ID | 错误描述（截断至 max_length 字符）
    请求 ID 用于关联日志中的完整堆栈信息。
    """
    trace_id = uuid4().hex[:8]
    msg = str(e)[:max_length]
    if len(str(e)) > max_length:
        msg += "..."
    return f"[{trace_id}] {msg}"


def safe_error_detail(e: Exception) -> str:
    """用于 HTTPException detail 字段的安全错误信息"""
    return safe_error(e, max_length=200)
