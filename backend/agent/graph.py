"""
Agent 核心编排 — LangGraph StateGraph + ThreadPoolExecutor 层内并行

架构（V3.0）：
    planner → executor (DAG并行) → reporter → END

LangGraph 负责：顶层流控制、State管理、SSE流式事件
ThreadPoolExecutor 负责：同层任务并行执行（最多4线程）
"""
import json
import time
from typing import TypedDict, List, Optional, Generator, Union, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

from langgraph.graph import StateGraph, END

from .schemas import AnalysisTask, TaskResult, AnalysisPlan
from .planner import Planner, BUILTIN_TEMPLATES
from .executor import Executor, ToolRegistry
from .reporter import Reporter
from .tools.data_query import DataQueryTool
from .tools.financial_calc import FinancialCalcTool
from .tools.chart import ChartTool
from utils.logger import TraceTimer, set_trace_id
from rag.model_router import init_usage, save_token_usage


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
    verification: Optional[dict]  # V6.0: 校验结果
    comparison: Optional[dict]    # V6.0: 对比结果


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
        _tool_registry.register(FinancialCalcTool())
        _tool_registry.register(ChartTool())
        # ── MCP 工具（阶段三）──
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


# DAG 拓扑排序 — 统一使用 utils.topological
from utils.topological import topological_layers as _topological_layers


# ==================== 节点函数 ====================

def planner_node(state: AgentState) -> dict:
    """Planner 节点：分析需求 → 任务列表"""
    _init_components()
    user_input = state["user_input"]
    template = state.get("template_name")
    session_id = state.get("session_id", "default")

    # ── V6.0: 加载用户偏好（长时记忆）──
    from .memory import UserMemory
    preferences = UserMemory().get_preferences(session_id)
    if preferences.get("preferred_company") and not template:
        # 有偏好公司且未指定模板：自动补全到查询中
        pref_company = preferences["preferred_company"]
        if pref_company not in user_input:
            user_input = f"{pref_company} {user_input}"
            logger.info(f"[Planner] 偏好注入: +{pref_company}")

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
    layers = _topological_layers(tasks_dict)
    logger.info(f"[Planner] 拆解完成: {len(tasks_dict)} 任务, {len(layers)} DAG层")
    for i, layer in enumerate(layers):
        logger.debug(f"  层{i}: {[t['task_id'] + ':' + t['task_type'] for t in layer]}")

    return {
        "clarification": None,
        "plan": plan.model_dump(),
        "tasks": tasks_dict,
        "task_results": [],
        "chart_count": 0,
    }


def executor_node(state: AgentState) -> dict:
    """
    Executor 节点：按 DAG 拓扑层并行执行所有任务。

    同一层的任务（无相互依赖）通过 ThreadPoolExecutor 并行提交，
    每层完成后才进入下一层（保证依赖关系）。
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
        # 拓扑分层
        layers = _topological_layers(pending)

        for layer_idx, layer in enumerate(layers):
            logger.info(f"[Executor] DAG 层 {layer_idx+1}/{len(layers)}: {len(layer)} 任务并行")

            def _execute_one(task_dict: dict) -> dict:
                """执行单个任务（线程安全）"""
                task = AnalysisTask(**task_dict)
                # 检查依赖
                for dep_id in task.depends_on:
                    dep = result_map.get(dep_id)
                    if dep and not dep.get("success", True):
                        return TaskResult(
                            task_id=task.task_id, task_type=task.task_type,
                            success=False,
                            error=f"前置任务 {dep_id} 失败，跳过「{task.description}」",
                        ).model_dump()

                dep_results = [TaskResult(**result_map[dep_id]) for dep_id in task.depends_on if dep_id in result_map]
                result = _executor.tools.execute_task(task, dep_results)
                return result.model_dump()

            # 层内并行执行
            layer_start = time.time()
            with ThreadPoolExecutor(max_workers=min(2, len(layer))) as pool:
                futures = {pool.submit(_execute_one, t): t["task_id"] for t in layer}
                for future in as_completed(futures):
                    task_id = futures[future]
                    try:
                        result_dict = future.result()
                        result_map[task_id] = result_dict
                    except Exception as e:
                        logger.error(f"[Executor] 任务 {task_id} 异常: {e}")
                        result_map[task_id] = TaskResult(
                            task_id=task_id, task_type="unknown",
                            success=False, error=str(e),
                        ).model_dump()
            layer_elapsed = time.time() - layer_start
            logger.debug(f"[Executor] DAG 层 {layer_idx+1} 耗时 {layer_elapsed:.2f}s")

    new_results = [result_map[t["task_id"]] for t in tasks_dict if t["task_id"] in result_map]
    chart_count = sum(1 for r in new_results if r.get("chart_base64"))

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


def verifier_node(state: AgentState) -> dict:
    """V6.0: 校验 Agent — 在报告生成前独立审查执行结果"""
    if state.get("clarification"):
        return {}
    tasks_dict = state.get("tasks", [])
    results_dict = state.get("task_results", [])
    if not results_dict:
        return {"verification": None}

    from .verifier import Verifier
    verifier = Verifier()
    result = verifier.verify(
        state["user_input"], tasks_dict, results_dict,
    )
    logger.info(f"[Verifier] 校验完成: passed={result['passed']}, "
                f"issues={len(result['issues'])}, warnings={len(result['warnings'])}")
    return {"verification": result}


# ==================== 条件路由 ====================

def comparator_node(state: AgentState) -> dict:
    """V6.0: 对比 Agent — 从多公司结果中抽取指标生成对比表"""
    if state.get("clarification"):
        return {}
    results_dict = state.get("task_results", [])
    tasks_dict = state.get("tasks", [])
    if not results_dict:
        return {"comparison": None}

    from .comparator import Comparator
    comp = Comparator()
    result = comp.compare(tasks_dict, results_dict)
    logger.info(f"[Comparator] 对比完成: {result['summary']}")
    return {"comparison": result}


def _route_after_planner(state: AgentState) -> str:
    """Planner 之后：有追问→reporter，否则→executor"""
    if state.get("clarification"):
        return "reporter"
    return "executor"


def _route_after_verifier(state: AgentState) -> str:
    """V6.0: 校验后路由 — 多公司对比模板走 comparator，否则直通 reporter"""
    template = state.get("template_name", "")
    if template == "cross_company_profit":
        return "comparator"
    return "reporter"


# ==================== 构建 Graph ====================

def _build_agent_graph() -> StateGraph:
    """构建 LangGraph StateGraph"""
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("verifier", verifier_node)       # V6.0: 校验Agent
    builder.add_node("comparator", comparator_node)    # V6.0: 对比Agent
    builder.add_node("reporter", reporter_node)

    builder.set_entry_point("planner")
    builder.add_conditional_edges("planner", _route_after_planner, {
        "executor": "executor",
        "reporter": "reporter",
    })
    builder.add_edge("executor", "verifier")
    builder.add_conditional_edges("verifier", _route_after_verifier, {
        "comparator": "comparator",
        "reporter": "reporter",
    })
    builder.add_edge("comparator", "reporter")
    builder.add_edge("reporter", END)

    return builder.compile()


# 全局 Graph 实例（懒编译）
_agent_graph = None


def _get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = _build_agent_graph()
    return _agent_graph


# ==================== 分析历史持久化（V6.0） ====================

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
    # ── V6.0: 同步写入 token 用量 + 更新用户偏好（与 analysis_log 一起落盘）──
    save_token_usage(session_id, f"agent_{status}")
    from .memory import UserMemory
    UserMemory().update_from_query(session_id, user_input)
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
    流式执行 Agent 分析，yield SSE 事件字符串。

    通过 LangGraph graph.stream() 获取节点事件，
    包装为前端可消费的 SSE 格式。
    """
    _init_components()
    start_time = time.time()
    tid = set_trace_id()  # 生成本次请求的 trace_id
    init_usage()  # V6.0: 初始化 token 计数

    try:
        graph = _get_agent_graph()
        initial_state: AgentState = {
            "user_input": user_input,
            "session_id": session_id,
            "template_name": template_name,
        }

        logger.info(f"[请求开始] session={session_id}, query={user_input[:80]}")
        yield AgentEvent("plan_start", message="正在分析需求...").to_sse()

        # LangGraph stream 逐节点产出状态
        last_state = initial_state
        task_count = 0
        prev_result_count = 0
        prev_chart_count = 0

        for event in graph.stream(initial_state, stream_mode="values"):
            # event 是一个 dict，包含更新后的状态
            combined_state = {**last_state, **event}
            last_state = combined_state

            # 检查是否需要追问
            if combined_state.get("clarification"):
                yield AgentEvent(
                    "clarification",
                    question=combined_state["clarification"],
                    message="需要更多信息",
                ).to_sse()
                return

            # 任务规划完成
            tasks = combined_state.get("tasks", [])
            if tasks and task_count == 0:
                task_count = len(tasks)
                yield AgentEvent(
                    "plan_start",
                    task_count=task_count,
                    tasks=[{"id": t["task_id"], "type": t["task_type"], "desc": t.get("description", "")} for t in tasks],
                    message=f"已规划 {task_count} 个子任务",
                ).to_sse()

            # 任务执行进度
            results = combined_state.get("task_results", [])
            if len(results) > prev_result_count:
                for i, r in enumerate(results[prev_result_count:]):
                    task_idx = prev_result_count + i + 1
                    # 先发 task_start（前端进度条依赖此事件）
                    task_info = next((t for t in tasks if t["task_id"] == r["task_id"]), None)
                    yield AgentEvent(
                        "task_start",
                        task_id=r["task_id"],
                        description=task_info.get("description", "") if task_info else "",
                        task_idx=task_idx,
                        total=task_count,
                        message=f"开始执行任务 [{task_idx}/{task_count}]",
                    ).to_sse()
                    if r.get("chart_base64"):
                        yield AgentEvent(
                            "chart",
                            task_id=r["task_id"],
                            chart_base64=r["chart_base64"],
                            chart_index=combined_state.get("chart_count", 0),
                            message=f"图表已生成",
                        ).to_sse()
                    yield AgentEvent(
                        "task_complete",
                        task_id=r["task_id"],
                        success=r.get("success", False),
                        summary=r.get("summary", ""),
                        error=r.get("error"),
                        message=f"{'✅' if r.get('success') else '❌'} {r.get('summary') or r.get('error') or '任务完成'}",
                    ).to_sse()
                prev_result_count = len(results)
                prev_chart_count = combined_state.get("chart_count", 0)

            # 报告生成完成
            if combined_state.get("final_report"):
                report = combined_state["final_report"]
                processing_time = round(time.time() - start_time, 1)
                charts = [r.get("chart_base64") for r in results if r.get("chart_base64")]

                yield AgentEvent(
                    "done",
                    report=report,
                    charts=charts,
                    task_count=len(results),
                    processing_time=processing_time,
                    message=f"分析完成，耗时 {processing_time} 秒",
                ).to_sse()
                # ── V6.0: 持久化分析记录 ──
                save_analysis_log(
                    session_id, user_input, template_name,
                    task_count=len(results),
                    task_details=[{"task_id": r.get("task_id"), "type": r.get("task_type", ""),
                                   "success": r.get("success", False)} for r in results],
                    report=report, chart_count=chart_count,
                    processing_time=processing_time,
                )
                logger.info(f"[请求结束] trace_id={tid}, 总耗时={processing_time}s, tasks={len(results)}")
                return

        # 如果流结束了但没有 final_report，再跑一次 reporter（兜底）
        if not last_state.get("final_report") and not last_state.get("clarification"):
            tasks_dict = last_state.get("tasks", [])
            results_dict = last_state.get("task_results", [])
            chart_count = last_state.get("chart_count", 0)
            tasks = [AnalysisTask(**t) for t in tasks_dict]
            results = [TaskResult(**r) for r in results_dict]
            with TraceTimer("reporter_fallback"):
                report = _reporter.generate(user_input, tasks, results, chart_count)
            processing_time = round(time.time() - start_time, 1)
            yield AgentEvent(
                "done",
                report=report,
                charts=[r.get("chart_base64") for r in results_dict if r.get("chart_base64")],
                task_count=len(results),
                processing_time=processing_time,
                message=f"分析完成，耗时 {processing_time} 秒",
            ).to_sse()
            # ── V6.0: 持久化分析记录 ──
            save_analysis_log(
                session_id, user_input, template_name,
                task_count=len(results),
                task_details=[{"task_id": r.get("task_id"), "type": r.get("task_type", ""),
                               "success": r.get("success", False)} for r in results],
                report=report, chart_count=chart_count,
                processing_time=processing_time,
            )
            logger.info(f"[请求结束] trace_id={tid}, 总耗时={processing_time}s, tasks={len(results)}")

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
    tid = set_trace_id()  # 生成本次请求的 trace_id

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
        chart_count = sum(1 for r in results if r.chart_base64)
        report = _reporter.generate(user_input, plan.tasks, results, chart_count)
        processing_time = round(time.time() - start_time, 1)
        result = {
            "report": report,
            "charts": [r.chart_base64 for r in results if r.chart_base64],
            "task_count": len(plan.tasks),
            "processing_time": processing_time,
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
        "task_count": len(task_results),
        "processing_time": processing_time,
    }
    save_analysis_log(session_id, user_input, template_name,
                      task_count=len(task_results),
                      task_details=[{"task_id": r.get("task_id"), "type": r.get("task_type", ""),
                                     "success": r.get("success", False)} for r in task_results],
                      report=report, chart_count=chart_count,
                      processing_time=processing_time)
    return result
