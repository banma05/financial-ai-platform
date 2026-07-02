"""
LangGraph StateGraph — Agent 核心编排

三节点流程：
    planner → executor → (条件路由) → reporter → END
                             └→ executor（还有未完成任务）

V2.5 MVP: 简单线性执行（3 节点 + 条件循环）
V3.0 增强: DAG 拓扑排序 + 并行执行
"""
import json
import time
from typing import TypedDict, List, Optional, Any, Generator
from loguru import logger

from .schemas import AnalysisTask, TaskResult, AnalysisPlan, ChartConfig
from .planner import Planner, BUILTIN_TEMPLATES
from .executor import Executor, ToolRegistry
from .reporter import Reporter
from .tools.data_query import DataQueryTool
from .tools.financial_calc import FinancialCalcTool
from .tools.chart import ChartTool


# ==================== State 定义 ====================

class AgentState(TypedDict, total=False):
    """LangGraph 节点间传递的共享状态"""
    user_input: str                          # 原始用户输入
    session_id: str                          # 会话 ID
    template_name: Optional[str]             # 分析模板名
    tasks: List[dict]                        # 子任务列表（序列化）
    current_task_idx: int                    # 当前执行到的任务索引
    task_results: List[dict]                 # 各任务执行结果（序列化）
    chart_count: int                         # 生成的图表数量
    final_report: str                        # 最终报告
    error: Optional[str]                     # 错误信息
    clarification: Optional[str]             # 追问内容
    processing_time: float                   # 总耗时


# ==================== 全局单例 ====================

_agent_app = None
_tool_registry: Optional[ToolRegistry] = None
_planner: Optional[Planner] = None
_executor: Optional[Executor] = None
_reporter: Optional[Reporter] = None


def _init_components():
    """初始化 Agent 组件（懒加载）"""
    global _tool_registry, _planner, _executor, _reporter
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
        _tool_registry.register(DataQueryTool())
        _tool_registry.register(FinancialCalcTool())
        _tool_registry.register(ChartTool())

        _planner = Planner()
        _executor = Executor(_tool_registry)
        _reporter = Reporter()


# ==================== 节点函数 ====================

def planner_node(state: AgentState) -> dict:
    """Planner 节点：分析需求 → 子任务列表"""
    _init_components()

    user_input = state["user_input"]
    template = state.get("template_name")

    logger.info(f"[Planner] 开始拆解任务: {user_input[:50]}...")

    try:
        plan: AnalysisPlan = _planner.plan(user_input, template)

        if plan.requires_clarification:
            logger.info(f"[Planner] 需要追问: {plan.requires_clarification}")
            return {
                "clarification": plan.requires_clarification,
                "tasks": [],
                "current_task_idx": 0,
                "chart_count": 0,
            }

        # 序列化任务列表
        tasks_dict = [t.model_dump() for t in plan.tasks]
        logger.info(f"[Planner] 拆解完成，共 {len(tasks_dict)} 个子任务")

        return {
            "clarification": None,
            "tasks": tasks_dict,
            "current_task_idx": 0,
            "chart_count": 0,
        }
    except Exception as e:
        logger.error(f"[Planner] 拆解失败: {e}")
        return {
            "clarification": None,
            "tasks": [{
                "task_id": "1", "task_type": "data_query",
                "description": f"查询「{user_input}」相关数据", "params": {"query": user_input}
            }],
            "current_task_idx": 0,
            "chart_count": 0,
        }


def executor_node(state: AgentState) -> dict:
    """Executor 节点：按序执行当前任务"""
    _init_components()

    idx = state.get("current_task_idx", 0)
    tasks_dict = state.get("tasks", [])
    existing_results = state.get("task_results", [])

    if idx >= len(tasks_dict):
        return {}  # 所有任务已完成

    task_dict = tasks_dict[idx]
    task = AnalysisTask(**task_dict)
    logger.info(f"[Executor] 执行任务 [{task.task_id}]: {task.description}")

    try:
        # 将已有结果反序列化为 TaskResult 列表供依赖注入
        dep_results = [TaskResult(**r) for r in existing_results]

        # 执行单个任务
        result = _executor.tools.execute_task(task, dep_results)

        new_results = existing_results + [result.model_dump()]

        # 检查是否生成了图表
        chart_count = state.get("chart_count", 0)
        if result.chart_base64:
            chart_count += 1

        return {
            "task_results": new_results,
            "current_task_idx": idx + 1,
            "chart_count": chart_count,
        }

    except Exception as e:
        logger.error(f"[Executor] 任务 [{task.task_id}] 异常: {e}")
        error_result = TaskResult(
            task_id=task.task_id,
            task_type=task.task_type,
            success=False,
            error=str(e),
        )
        new_results = existing_results + [error_result.model_dump()]
        return {
            "task_results": new_results,
            "current_task_idx": idx + 1,
        }


def reporter_node(state: AgentState) -> dict:
    """Reporter 节点：生成最终报告"""
    _init_components()

    # 如果需要追问，生成追问报告
    if state.get("clarification"):
        return {
            "final_report": f"### ⚠️ 需要更多信息\n\n{state['clarification']}\n\n请补充信息后重试。",
        }

    user_input = state["user_input"]
    tasks_dict = state.get("tasks", [])
    results_dict = state.get("task_results", [])
    chart_count = state.get("chart_count", 0)

    tasks = [AnalysisTask(**t) for t in tasks_dict]
    results = [TaskResult(**r) for r in results_dict]

    logger.info(f"[Reporter] 生成报告: {len(tasks)} 任务, {len(results)} 结果")

    try:
        report = _reporter.generate(user_input, tasks, results, chart_count)
        return {"final_report": report}
    except Exception as e:
        logger.error(f"[Reporter] 生成失败: {e}")
        return {"final_report": f"## 分析报告生成失败\n\n错误: {e}"}


# ==================== 条件路由 ====================

def _should_continue(state: AgentState) -> str:
    """判断是否继续执行 executor"""
    if state.get("clarification"):
        return "reporter"  # 需要追问，直接到 reporter

    idx = state.get("current_task_idx", 0)
    total = len(state.get("tasks", []))

    if idx >= total:
        return "reporter"  # 所有任务完成

    return "executor"  # 继续执行下一个任务


# ==================== 流式事件发射器 ====================

class AgentEvent:
    """SSE 事件数据类"""
    def __init__(self, event_type: str, **kwargs):
        self.type = event_type
        self.data = kwargs

    def to_sse(self) -> str:
        return f"data: {json.dumps({'type': self.type, **self.data}, ensure_ascii=False)}\n\n"


def run_agent_stream(
    user_input: str,
    session_id: str = "default",
    template_name: Optional[str] = None,
) -> Generator[str, None, None]:
    """
    流式执行 Agent 分析，yield SSE 事件字符串。

    用法（FastAPI 端点）:
        for sse_event in run_agent_stream(query, session_id):
            yield sse_event

    事件序列：
    1. plan_start    — 开始规划，含任务数
    2. task_start    — 开始执行某个子任务
    3. task_complete — 子任务执行完成
    4. chart         — 图表生成（base64）
    5. report_start  — 开始生成报告
    6. done          — 分析完成，含报告文本
    7. error         — 分析出错
    8. clarification — 需要追问用户
    """
    _init_components()
    start_time = time.time()

    try:
        # Phase 1: Planner
        logger.info(f"[Agent] 开始分析: {user_input[:60]}...")
        yield AgentEvent("plan_start", message="正在分析需求...").to_sse()

        plan: AnalysisPlan = _planner.plan(user_input, template_name)

        if plan.requires_clarification:
            yield AgentEvent(
                "clarification",
                question=plan.requires_clarification,
                message="需要更多信息",
            ).to_sse()
            return

        tasks = plan.tasks
        yield AgentEvent(
            "plan_start",
            task_count=len(tasks),
            tasks=[{"id": t.task_id, "type": t.task_type, "desc": t.description} for t in tasks],
            message=f"已规划 {len(tasks)} 个子任务",
        ).to_sse()

        # Phase 2: Executor（逐个执行）
        results: List[TaskResult] = []
        chart_count = 0

        for i, task in enumerate(tasks):
            yield AgentEvent(
                "task_start",
                task_id=task.task_id,
                task_idx=i + 1,
                total=len(tasks),
                description=task.description,
                message=f"执行中: {task.description}",
            ).to_sse()

            # 执行任务
            dep_results = results  # 前置任务结果
            result = _executor.tools.execute_task(task, dep_results)
            results.append(result)

            # 推送图表
            if result.chart_base64:
                chart_count += 1
                yield AgentEvent(
                    "chart",
                    task_id=task.task_id,
                    chart_base64=result.chart_base64,
                    chart_index=chart_count,
                    message=f"图表 {chart_count} 已生成",
                ).to_sse()

            # 推送完成事件
            yield AgentEvent(
                "task_complete",
                task_id=task.task_id,
                task_idx=i + 1,
                total=len(tasks),
                success=result.success,
                summary=result.summary,
                error=result.error,
                message=f"{'✅' if result.success else '❌'} {result.summary or result.error or task.description}",
            ).to_sse()

        # Phase 3: Reporter
        yield AgentEvent("report_start", message="正在生成分析报告...").to_sse()

        report = _reporter.generate(user_input, tasks, results, chart_count)

        processing_time = round(time.time() - start_time, 1)

        yield AgentEvent(
            "done",
            report=report,
            charts=[r.chart_base64 for r in results if r.chart_base64],
            task_count=len(tasks),
            processing_time=processing_time,
            message=f"分析完成，耗时 {processing_time} 秒",
        ).to_sse()

    except Exception as e:
        logger.error(f"[Agent] 分析异常: {e}")
        yield AgentEvent("error", message=str(e)).to_sse()


def run_agent_sync(
    user_input: str,
    session_id: str = "default",
    template_name: Optional[str] = None,
) -> dict:
    """
    同步执行 Agent 分析（非流式）。

    返回:
        {
            "report": str,        # Markdown 报告
            "charts": List[str],  # 图表 base64 列表
            "task_count": int,    # 执行子任务数
            "processing_time": float,  # 总耗时
        }
    """
    _init_components()
    start_time = time.time()

    # Planner
    plan = _planner.plan(user_input, template_name)
    if plan.requires_clarification:
        return {
            "report": f"### ⚠️ 需要更多信息\n\n{plan.requires_clarification}",
            "charts": [],
            "task_count": 0,
            "processing_time": round(time.time() - start_time, 1),
            "clarification": plan.requires_clarification,
        }

    # Executor
    results = _executor.execute(plan.tasks)
    chart_count = sum(1 for r in results if r.chart_base64)

    # Reporter
    report = _reporter.generate(user_input, plan.tasks, results, chart_count)

    processing_time = round(time.time() - start_time, 1)

    return {
        "report": report,
        "charts": [r.chart_base64 for r in results if r.chart_base64],
        "task_count": len(plan.tasks),
        "processing_time": processing_time,
    }
