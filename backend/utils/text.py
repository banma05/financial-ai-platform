"""
文本处理工具 — JSON 清理、Markdown 代码块剥离

消除项目中多处重复的 LLM JSON 响应清理逻辑。
"""
import json
import re
from typing import Any


def clean_json_response(text: str) -> str:
    """
    清理 LLM 返回的 JSON 字符串，处理常见格式噪声。

    处理步骤：
    1. 剥离 ```json / ``` 代码块标记
    2. 去除尾部多余字符（LLM 经常在 JSON 后追加解释文字）
    3. 截断到最后一个完整闭合的大括号

    参数:
        text: LLM 原始响应文本

    返回:
        清理后的纯 JSON 字符串（可安全传给 json.loads）
    """
    text = text.strip()

    # 1. 剥离 Markdown 代码块标记
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉第一行（```json 或 ```）
        # 如果最后一行是 ```，也去掉
        if lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
        else:
            text = "\n".join(lines[1:])

    # 2. 去除尾部逗号（含 "},]" 前的逗号，LLM 常见于截断输出）
    import re as _re
    text = text.rstrip()
    text = _re.sub(r',\s*([}\]])', r'\1', text)  # "1,}" → "1}", "2,]" → "2]"

    # 3. 找到第一个完整闭合的 JSON 对象，截断后面的多余内容
    #    （处理 LLM 输出 "{\"a\":1}{\"b\":2}" 或 "{\"a\":1}以上是提取结果"）
    brace_count = 0
    for pos, ch in enumerate(text):
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
            if brace_count == 0:
                # 第一个完整 JSON 对象结束，只取到这里
                text = text[:pos + 1]
                break

    return text


def parse_llm_json(text: str) -> Any:
    """
    安全解析 LLM 返回的 JSON：清理 + json.loads 一步完成。

    参数:
        text: LLM 原始响应文本

    返回:
        解析后的 Python 对象

    异常:
        json.JSONDecodeError: JSON 格式无效（调用方负责降级处理）
    """
    return json.loads(clean_json_response(text))
