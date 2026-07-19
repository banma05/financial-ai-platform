"""
Agent 核心编排 — LangGraph StateGraph 三节点直通

架构（V8.0 重构）：
    planner → executor → reporter → END

设计原则：SQL 优先查数字，RAG 辅助解读本文，零冗余节点。
"""
import json
import time
from typing import TypedDict, List, Optional, Generator, Dict, Any
from loguru import logger

from langgraph.graph import StateGraph, END

from .schemas import AnalysisTask, TaskResult, AnalysisPlan
from .planner import Planner, BUILTIN_TEMPLATES
from .executor import Executor, ToolRegistry
from .reporter import Reporter
from .tools.data_query import DataQueryTool
from .tools.financial_calc import FinancialCalcTool
from .tools.chart import ChartTool
from .tools.rag_context import RAGContextTool
from utils.logger import TraceTimer, set_trace_id
from rag.model_router import init_usage, save_token_usage
# AGENT_TASK_TIMEOUT 不再在 executor_node 中使用（V8.2 安全修复：移除 ThreadPoolExecutor 嵌套）
# 超时保护由 OpenAI client(60s) + 熔断器(5次→OPEN) 提供


# ==================== State 定义 ====================

class AgentState(TypedDict, total=False):
    """LangGraph Agent 共享状态"""
    user_input: str
    session_id: str
    template_name: Optional[str]
    plan: Optional[dict]        # AnalysisPlan 序列化
    tasks: List[dict]           # AnalysisTask 序列化列表
    task_results: List[dict]    # TaskResult 序列化列表
    chart_count: int
    final_report: str
    clarification: Optional[str]
    processing_time: float
    error: Optional[str]


# ==================== 全局单例 ====================

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
        _tool_registry.register(RAGContextTool())
        _tool_registry.register(FinancialCalcTool())
        _tool_registry.register(ChartTool())
        # ── MCP 工具 ──
        from mcp import (
            StockPriceTool, FinancialStatementsTool, CalculateRatioTool,
            IndustryComparisonTool, MarketIndexTool, FinancialCalendarTool,
        )
        _tool_registry.register(StockPriceTool())
        _tool_registry.register(FinancialStatementsTool())
        _tool_registry.register(CalculateRatioTool())
        _tool_registry.register(IndustryComparisonTool())
        _tool_registry.register(MarketIndexTool())
        _tool_registry.register(FinancialCalendarTool())
        _planner = Planner()
        _executor = Executor(_tool_registry)
        _reporter = Reporter()


# ==================== 节点函数 ====================

def planner_node(state: AgentState) -> dict:
    """Planner 节点：分析需求 → 任务列表"""
    _init_components()
    user_input = state["user_input"]
    template = state.get("template_name")

    logger.info(f"[Planner] 开始拆解: {user_input[:50]}...")

    with TraceTimer("planner"):
        try:
            plan: AnalysisPlan = _planner.plan(user_input, template)
        except Exception as e:
            logger.error(f"[Planner] 拆解失败: {e}")
            return {
                "clarification": None,
                "tasks": [{
                    "task_id": "1", "task_type": "data_query",
                    "description": f"查询「{user_input}」相关数据",
                    "params": {"query": user_input},
                }],
                "chart_count": 0,
            }

    if plan.requires_clarification:
        logger.info(f"[Planner] 需要追问: {plan.requires_clarification}")
        return {
            "clarification": plan.requires_clarification,
            "tasks": [],
            "chart_count": 0,
        }

    tasks_dict = [t.model_dump() for t in plan.tasks]
    logger.info(f"[Planner] 拆解完成: {len(tasks_dict)} 任务")

    return {
        "clarification": None,
        "plan": plan.model_dump(),
        "tasks": tasks_dict,
        "task_results": [],
        "chart_count": 0,
    }


def executor_node(state: AgentState) -> dict:
    """
    Executor 节点：按依赖顺序线性执行所有任务。

    V8.0: 回归线性执行。避免 ThreadPoolExecutor 与懒加载单例的竞态条件，
    以及 GPU 模型双重加载导致 CUDA OOM 的问题。
    层内并行收益有限（多数模板只有 1-2 个无依赖任务），不值得为它引入线程复杂度。
    """
    _init_components()
    tasks_dict = state.get("tasks", [])
    all_results = state.get("task_results", [])

    if not tasks_dict:
        return {}

    # 按 task_id 建立已有结果索引
    result_map: Dict[str, dict] = {r["task_id"]: r for r in all_results}
    # 找出尚未完成的任务
    pending = [t for t in tasks_dict if t["task_id"] not in result_map]

    if not pending:
        logger.info("[Executor] 所有任务已完成")
        return {}

    with TraceTimer("executor"):
        # 按 task_id 排序，保证确定性执行顺序
        pending.sort(key=lambda t: t["task_id"])

        for task_dict in pending:
            task = AnalysisTask(**task_dict)
            logger.info(f"[Executor] 执行: {task.task_id}:{task.task_type} — {task.description[:40]}")

            # 检查前置依赖是否失败
            for dep_id in task.depends_on:
                dep = result_map.get(dep_id)
                if dep and not dep.get("success", True):
                    result_map[task.task_id] = TaskResult(
                        task_id=task.task_id, task_type=task.task_type,
                        success=False,
                        error=f"前置任务 {dep_id} 失败，跳过「{task.description}」",
                    ).model_dump()
                    break
            else:
                # 依赖正常，执行任务
                dep_results = [
                    TaskResult(**result_map[dep_id])
                    for dep_id in task.depends_on if dep_id in result_map
                ]
                try:
                    # V8.2: 直接调用执行（已有多层超时保护）
                    # - OpenAI client 层：60s 超时（model_router.py:111）
                    # - LLM 熔断器：5 次连续失败→熔断，30s 冷却（model_router.py:98-102）
                    # - 不再使用 ThreadPoolExecutor(max_workers=1) 嵌套线程：
                    #   V6.1 已发现 DAG 并行+线程嵌套导致 GPU 双重加载→OOM，
                    #   ThreadPoolExecutor 嵌套同样有线程调度开销+锁竞争风险→系统不稳定
                    result = _executor.tools.execute_task(task, dep_results)
                    result_map[task.task_id] = result.model_dump()
                except Exception as e:
                    logger.error(f"[Executor] 任务 {task.task_id} 异常: {e}")
                    result_map[task.task_id] = TaskResult(
                        task_id=task.task_id, task_type=task.task_type,
                        success=False, error=str(e),
                    ).model_dump()

    new_results = [result_map[t["task_id"]] for t in tasks_dict if t["task_id"] in result_map]
    chart_count = sum(1 for r in new_results if r.get("chart_option") or r.get("chart_base64"))

    return {"task_results": new_results, "chart_count": chart_count}


def reporter_node(state: AgentState) -> dict:
    """Reporter 节点：生成最终分析报告"""
    _init_components()

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

    logger.info(f"[Reporter] 生成报告: {len(tasks)} 任务, {len(results)} 结果, {chart_count} 图表")

    with TraceTimer("reporter"):
        try:
            report = _reporter.generate(user_input, tasks, results, chart_count)
            return {"final_report": report}
        except Exception as e:
            logger.error(f"[Reporter] 生成失败: {e}")
            return {"final_report": f"## 分析报告生成失败\n\n错误: {e}"}


# ==================== 条件路由 ====================

def _route_after_planner(state: AgentState) -> str:
    """Planner 之后：有追问→reporter，否则→executor"""
    if state.get("clarification"):
        return "reporter"
    return "executor"


# ==================== 构建 Graph ====================

def _build_agent_graph() -> StateGraph:
    """构建 LangGraph StateGraph：planner → executor → reporter → END"""
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("reporter", reporter_node)

    builder.set_entry_point("planner")
    builder.add_conditional_edges("planner", _route_after_planner, {
        "executor": "executor",
        "reporter": "reporter",
    })
    builder.add_edge("executor", "reporter")
    builder.add_edge("reporter", END)

    return builder.compile()


# 全局 Graph 实例（懒编译）
_agent_graph = None


def _get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = _build_agent_graph()
    return _agent_graph


# ==================== 分析历史持久化 ====================

def save_analysis_log(
    session_id: str, user_input: str, template_name: str = "",
    task_count: int = 0, task_details: list = None,
    report: str = "", chart_count: int = 0,
    processing_time: float = 0.0, status: str = "completed",
):
    """
    持久化 Agent 分析记录到 analysis_log 表。
    写入失败不影响主流程（静默降级）。
    """
    from db import SessionLocal, AnalysisLog
    save_token_usage(session_id, f"agent_{status}")
    db = SessionLocal()
    try:
        log_entry = AnalysisLog(
            session_id=session_id,
            user_input=user_input,
            template_name=template_name or "",
            task_count=task_count,
            task_details=task_details or [],
            report=report,
            chart_count=chart_count,
            processing_time=processing_time,
            status=status,
        )
        db.add(log_entry)
        db.commit()
        logger.debug(f"AnalysisLog 已写入: session={session_id}, tasks={task_count}, time={processing_time}s")
    except Exception as e:
        db.rollback()
        logger.debug(f"AnalysisLog 写入失败（静默降级）: {e}")
    finally:
        db.close()


# ==================== 公共入口 ====================

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
    V8.3 重构：逐任务执行 + 实时推送 SSE。

    旧架构用 graph.stream() 只在节点边界推送事件——executor_node
    内所有任务跑完才一次性返回，导致进度条 25 秒空白后瞬间跳满。
    新架构 Planner 走 graph 拿计划，任务在 generator 中逐个执行，
    每完成一个立即 yield SSE——工作与推送真正并步。
    """
    _init_components()
    start_time = time.time()
    tid = set_trace_id()
    init_usage()

    try:
        graph = _get_agent_graph()
        initial_state: AgentState = {
            "user_input": user_input,
            "session_id": session_id,
            "template_name": template_name,
        }

        logger.info(f"[请求开始] session={session_id}, query={user_input[:80]}")
        yield AgentEvent("plan_start", message="正在分析需求...").to_sse()

        # ── Phase 1: Planner 走 graph ──
        plan_state = None
        for event in graph.stream(initial_state, stream_mode="values"):
            plan_state = {**initial_state, **event}
            if plan_state.get("clarification"):
                yield AgentEvent("clarification",
                    question=plan_state["clarification"],
                    message="需要更多信息").to_sse()
                return
            if plan_state.get("tasks"):
                break  # Planner 完成，立即开始逐任务执行

        tasks = plan_state.get("tasks", []) if plan_state else []
        if not tasks:
            yield AgentEvent("error", message="未能生成分析计划").to_sse()
            return

        task_count = len(tasks)
        yield AgentEvent("plan_start",
            task_count=task_count,
            tasks=[{"id": t["task_id"], "type": t["task_type"],
                    "desc": t.get("description", "")} for t in tasks],
            message=f"已规划 {task_count} 个子任务",
        ).to_sse()

        # ── Phase 2: 逐任务执行 + 实时推送 ──
        result_map: Dict[str, dict] = {}
        chart_count = 0

        for idx, task_dict in enumerate(tasks, 1):
            task = AnalysisTask(**task_dict)

            # 推 task_start
            yield AgentEvent("task_start",
                task_id=task.task_id,
                description=task.description or "",
                task_idx=idx, total=task_count,
                message=f"开始执行任务 [{idx}/{task_count}]",
            ).to_sse()

            # 检查前置依赖
            dep_failed = False
            for dep_id in task.depends_on:
                dep = result_map.get(dep_id)
                if dep and not dep.get("success", True):
                    dep_failed = True
                    break

            if dep_failed:
                result = TaskResult(
                    task_id=task.task_id, task_type=task.task_type,
                    success=False,
                    error=f"前置任务失败，跳过「{task.description}」",
                ).model_dump()
            else:
                dep_results = [
                    TaskResult(**result_map[dep_id])
                    for dep_id in task.depends_on if dep_id in result_map
                ]
                try:
                    result = _executor.tools.execute_task(task, dep_results)
                except Exception as e:
                    logger.error(f"[Executor] 任务 {task.task_id} 异常: {e}")
                    result = TaskResult(
                        task_id=task.task_id, task_type=task.task_type,
                        success=False, error=str(e),
                    )

            result_map[task.task_id] = result if isinstance(result, dict) else result.model_dump()
            r = result_map[task.task_id]

            # 图表事件（V8.3: 发送 ECharts option JSON + 解读说明）
            # V8.4: 支持多图互补 — 多张图表逐个推送 SSE 事件
            chart_opts = r.get("chart_options") or ([r["chart_option"]] if r.get("chart_option") else [])
            for ci, opt in enumerate(chart_opts):
                if opt:
                    chart_count += 1
                    yield AgentEvent("chart",
                        task_id=task.task_id,
                        chart_option=opt,
                        chart_description=r.get("chart_description", ""),
                        chart_index=chart_count,
                        message=f"图表 {chart_count} 已生成",
                    ).to_sse()

            # 推 task_complete
            yield AgentEvent("task_complete",
                task_id=task.task_id,
                success=r.get("success", False),
                summary=r.get("summary", ""),
                error=r.get("error"),
                message=f"{'✅' if r.get('success') else '❌'} {r.get('summary') or r.get('error') or '任务完成'} ({(time.time()-start_time):.1f}s)",
            ).to_sse()

        # ── Phase 3: Reporter 直接生成报告 ──
        task_results_list = [result_map[t["task_id"]] for t in tasks if t["task_id"] in result_map]
        task_objects = [AnalysisTask(**t) for t in tasks]
        result_objects = [TaskResult(**r) for r in task_results_list]

        with TraceTimer("reporter"):
            report = _reporter.generate(user_input, task_objects, result_objects, chart_count)

        processing_time = round(time.time() - start_time, 1)
        chart_options = [r.get("chart_option") for r in task_results_list if r.get("chart_option")]

        yield AgentEvent("done",
            report=report,
            charts=[],  # V8.3: 已弃用 base64，保留字段向后兼容
            chart_options=chart_options,
            task_count=len(task_results_list),
            processing_time=processing_time,
            message=f"分析完成，耗时 {processing_time} 秒",
        ).to_sse()

        save_analysis_log(
            session_id, user_input, template_name,
            task_count=len(task_results_list),
            task_details=[{"task_id": r.get("task_id"), "type": r.get("task_type", ""),
                           "success": r.get("success", False)} for r in task_results_list],
            report=report, chart_count=chart_count,
            processing_time=processing_time,
        )
        logger.info(f"[请求结束] trace_id={tid}, 总耗时={processing_time}s, tasks={len(task_results_list)}")

    except Exception as e:
        logger.error(f"[Agent] 分析异常: trace_id={tid}, error={e}")
        yield AgentEvent("error", message=str(e)).to_sse()


def run_agent_sync(
    user_input: str,
    session_id: str = "default",
    template_name: Optional[str] = None,
    plan: AnalysisPlan = None,
) -> dict:
    """
    同步执行 Agent 分析（非流式）。通过 LangGraph graph.invoke()

    参数:
        plan: 可选，预生成的 AnalysisPlan。传入后跳过 Planner 步骤。
    """
    _init_components()
    start_time = time.time()
    tid = set_trace_id()

    # 如已有 plan 则跳过 Planner（benchmark 复用优化）
    if plan is not None:
        if plan.requires_clarification:
            result = {
                "report": f"### ⚠️ 需要更多信息\n\n{plan.requires_clarification}",
                "charts": [],
                "task_count": 0,
                "processing_time": round(time.time() - start_time, 1),
                "clarification": plan.requires_clarification,
            }
            save_analysis_log(session_id, user_input, template_name,
                              task_count=0, report=result["report"],
                              processing_time=result["processing_time"], status="clarification")
            return result
        results = _executor.execute(plan.tasks)
        chart_count = sum(1 for r in results if r.chart_option or r.chart_base64)
        report = _reporter.generate(user_input, plan.tasks, results, chart_count)
        processing_time = round(time.time() - start_time, 1)
        result = {
            "report": report,
            "charts": [r.chart_base64 for r in results if r.chart_base64],
            "chart_options": [r.chart_option for r in results if r.chart_option],
            "task_count": len(plan.tasks),
            "processing_time": processing_time,
            "task_results": [r.model_dump() for r in results],  # V8.2: 供评测提取 data_values
        }
        save_analysis_log(session_id, user_input, template_name,
                          task_count=len(plan.tasks),
                          task_details=[{"task_id": r.task_id, "type": r.task_type,
                                         "success": r.success} for r in results],
                          report=report, chart_count=chart_count,
                          processing_time=processing_time)
        return result

    # 正常流程：通过 LangGraph
    graph = _get_agent_graph()
    initial_state: AgentState = {
        "user_input": user_input,
        "session_id": session_id,
        "template_name": template_name,
    }

    try:
        final_state = graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"[Agent] 同步执行失败: {e}")
        processing_time = round(time.time() - start_time, 1)
        result = {
            "report": f"## 分析异常\n\n错误: {e}",
            "charts": [],
            "task_count": 0,
            "processing_time": processing_time,
        }
        save_analysis_log(session_id, user_input, template_name,
                          task_count=0, report=result["report"],
                          processing_time=processing_time, status="failed")
        return result

    processing_time = round(time.time() - start_time, 1)
    task_results = final_state.get("task_results", [])
    report = final_state.get("final_report", "## 报告生成失败")
    chart_count = final_state.get("chart_count", 0)
    result = {
        "report": report,
        "charts": [r.get("chart_base64") for r in task_results if r.get("chart_base64")],
        "chart_options": [r.get("chart_option") for r in task_results if r.get("chart_option")],
        "task_count": len(task_results),
        "processing_time": processing_time,
        "task_results": task_results,  # V8.2: 供评测提取 data_values
    }
    save_analysis_log(session_id, user_input, template_name,
                      task_count=len(task_results),
                      task_details=[{"task_id": r.get("task_id"), "type": r.get("task_type", ""),
                                     "success": r.get("success", False)} for r in task_results],
                      report=report, chart_count=chart_count,
                      processing_time=processing_time)
    return result
