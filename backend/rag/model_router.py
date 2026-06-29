"""
模型路由层 — 根据任务复杂度智能调度不同模型

策略：
- deepseek-v4-flash：简单任务（摘要、提取、分类），快且便宜
- deepseek-v4-pro：  复杂任务（财务分析、跨文档对比、异常检测），深度推理

面试可展开讲：
  为什么做模型路由、如何判断任务复杂度、成本能优化多少
"""
from enum import Enum
from typing import Optional
from loguru import logger
from openai import OpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, LLM_MODEL, REASONING_MODEL


class TaskType(str, Enum):
    SIMPLE = "simple"     # 用 flash，快便宜
    COMPLEX = "complex"   # 用 pro，深度推理
    AUTO = "auto"         # 自动判断


MODEL_CONFIG = {
    TaskType.SIMPLE: {
        "model": LLM_MODEL,  # deepseek-v4-flash
        "temperature": 0.3,
        "max_tokens": 2000,
    },
    TaskType.COMPLEX: {
        "model": REASONING_MODEL,  # deepseek-v4-pro
        "temperature": 0.3,
        "max_tokens": 4000,
    },
}

# 命中以下关键词 → 路由到推理模型
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
    """根据用户问题自动判断任务复杂度"""
    for kw in COMPLEX_KEYWORDS:
        if kw in query:
            logger.info(f"路由 → 推理模型（关键词: {kw}）")
            return TaskType.COMPLEX
    return TaskType.SIMPLE


def chat(
    messages: list,
    task_type: TaskType = TaskType.AUTO,
    query: Optional[str] = None,
) -> str:
    """
    带路由的 LLM 调用

    参数:
        messages: 标准 messages 列表
        task_type: SIMPLE / COMPLEX / AUTO
        query: 用户原始问题（AUTO 模式用于判断复杂度）
    """
    if query is None:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                query = msg.get("content", "")
                break

    target = classify(query) if task_type == TaskType.AUTO else task_type
    cfg = MODEL_CONFIG[target]
    client = _get_client()

    logger.info(f"模型路由: {target.value} → {cfg['model']}")

    response = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        temperature=cfg["temperature"],
        max_tokens=cfg["max_tokens"],
    )
    return response.choices[0].message.content
