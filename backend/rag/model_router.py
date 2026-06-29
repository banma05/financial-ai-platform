"""
模型调用层

当前统一使用 deepseek-v4-pro（最强模型），架构预留了多模型路由接口：
- 如果后续想加 flash 来省钱，只需改 MODEL_CONFIG 即可
- classify() 函数可自动判断任务复杂度
- 面试时可以展开讲这个架构设计思路
"""
from enum import Enum
from typing import Optional
from loguru import logger
from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, LLM_MODEL


class TaskType(str, Enum):
    SIMPLE = "simple"
    COMPLEX = "complex"
    AUTO = "auto"


# 当前都用 deepseek-v4-pro，想省钱时把 SIMPLE 换成 deepseek-v4-flash
MODEL_CONFIG = {
    TaskType.SIMPLE: {
        "model": LLM_MODEL,    # deepseek-v4-pro
        "temperature": 0.3,
        "max_tokens": 2000,
    },
    TaskType.COMPLEX: {
        "model": LLM_MODEL,    # deepseek-v4-pro
        "temperature": 0.3,
        "max_tokens": 4000,
    },
}

COMPLEX_KEYWORDS = [
    "分析", "对比", "趋势", "变化", "原因", "为什么",
    "异常", "风险", "评估", "判断", "预测", "建议",
    "关联", "影响", "差异", "波动", "增长", "下降",
    "指标", "比率", "毛利率", "净利率", "ROE", "ROA",
    "同比", "环比", "财务", "审计", "合规",
]

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


def classify(query: str) -> TaskType:
    """自动判断任务复杂度（为后续多模型路由预留）"""
    for kw in COMPLEX_KEYWORDS:
        if kw in query:
            return TaskType.COMPLEX
    return TaskType.SIMPLE


def chat(
    messages: list,
    task_type: TaskType = TaskType.AUTO,
    query: Optional[str] = None,
) -> str:
    """LLM 调用，支持按任务类型调整参数"""
    if query is None:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                query = msg.get("content", "")
                break

    target = classify(query) if task_type == TaskType.AUTO else task_type
    cfg = MODEL_CONFIG[target]
    client = _get_client()

    logger.info(f"模型: {cfg['model']} | 类型: {target.value}")

    response = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
    )
    return response.choices[0].message.content
