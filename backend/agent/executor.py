"""
Executor（工具执行编排器）+ ToolRegistry（工具注册中心）

职责：
1. ToolRegistry 管理所有可用工具（注册/查询/执行）
2. Executor 按依赖顺序执行子任务列表
3. 将前置任务的结果注入到后续任务参数中

V3.0: 依赖注入升级为三层回退（ParamInjector）
"""
from typing import List, Dict, Any, Callable
from loguru import logger

from .schemas import AnalysisTask, TaskResult
from .tools.param_injection import (
    ParamInjector,
    get_injector,
    parse_financial_value,
    FINANCIAL_TERM_TO_PARAM,
)


class ToolRegistry:
    """
    工具注册中心：管理所有可用工具。

    为模块三 MCP 预留扩展点——MCP 工具通过 register() 动态加入。
    """

    def __init__(self):
        self._tools: Dict[str, Any] = {}

    def register(self, tool: Any):
        """注册工具（tool 必须有 name 属性和 run() 方法）"""
        self._tools[tool.name] = tool
        logger.info(f"工具已注册: {tool.name}")

    def get(self, name: str):
        """获取工具，未找到返回 None"""
        tool = self._tools.get(name)
        if not tool:
            logger.warning(f"工具未注册: {name}，已注册: {list(self._tools.keys())}")
        return tool

    def list_tools(self) -> List[Dict[str, str]]:
        """列出所有已注册工具"""
        return [{"name": name, "type": type(t).__name__} for name, t in self._tools.items()]

    def execute_task(self, task: AnalysisTask, dependency_results: List[TaskResult] = None) -> TaskResult:
        """
        执行单个任务。

        流程：
        1. 根据 task_type 定位对应工具
        2. 将前置任务的结果注入到当前任务参数中
        3. 调用工具 run() 方法
        4. 格式化结果

        参数:
            task: 待执行的任务
            dependency_results: 前置任务的执行结果（用于参数注入）

        返回:
            TaskResult
        """
        # 任务类型 → 工具映射
        tool_map = {
            "data_query": "data_query",
            "calculate": "financial_calc",
            "chart": "chart",
            "analyze": None,    # analyze 不调用工具，由 Reporter 处理
            "compare": None,    # compare 由 Reporter 处理
        }

        tool_name = tool_map.get(task.task_type)
        if not tool_name:
            # analyze/compare 类型不需要工具执行，直接返回待分析的标记
            return TaskResult(
                task_id=task.task_id,
                task_type=task.task_type,
                success=True,
                summary=f"任务「{task.description}」等待分析",
                data={"task_type": task.task_type, "description": task.description},
            )

        tool = self.get(tool_name)
        if not tool:
            return TaskResult(
                task_id=task.task_id,
                task_type=task.task_type,
                success=False,
                summary="",
                error=f"未找到工具: {tool_name}",
            )

        try:
            # 注入前置任务的结果数据
            params = dict(task.params)
            if dependency_results:
                params = self._inject_dependency_data(task, dependency_results, params)

            # 调用工具
            result = tool.run(**params)

            # 格式化 TaskResult
            if task.task_type == "chart":
                return TaskResult(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    success=True,
                    summary=f"图表「{task.description}」已生成",
                    chart_base64=result if isinstance(result, str) else result.get("chart_base64"),
                    data=result,
                )
            elif task.task_type == "calculate":
                return TaskResult(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    success=result.get("success", False),
                    summary=result.get("expression", "") if result.get("success") else "",
                    data=result,
                    error=result.get("error"),
                )
            else:
                # data_query
                return TaskResult(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    success=result.get("found", False),
                    summary=result.get("summary", ""),
                    data=result,
                )

        except Exception as e:
            logger.error(f"任务执行失败 [{task.task_id}] {task.description}: {e}")
            return TaskResult(
                task_id=task.task_id,
                task_type=task.task_type,
                success=False,
                summary="",
                error=str(e),
            )

    def _inject_dependency_data(
        self, task: AnalysisTask, dependency_results: List[TaskResult], params: dict
    ) -> dict:
        """
        将前置任务的结果注入到当前任务参数。

        核心流程：
        1. 从 data_query 的结果中提取结构化数据
        2. 展平嵌套结构（LLM 可能返回 {"公司名": {...}} 等）
        3. 委托 ParamInjector 做三层回退注入（Level1→Level2→Level3）
        4. 合并到当前任务参数中（不覆盖已有参数）

        V3.0: 接入 ParamInjector 三层回退（精确映射 + 编辑距离 + LLM语义）
        """
        injector = get_injector()
        result_map = {r.task_id: r for r in dependency_results if r.success}

        for dep_id in task.depends_on:
            dep_result = result_map.get(dep_id)
            if not dep_result:
                continue

            # 从前置任务结果中提取结构化数据
            dep_data = dep_result.data
            if not isinstance(dep_data, dict):
                continue

            # data_query 结果：{"found": true, "data": {...}, ...}
            # calculate 结果：{"success": true, "result": ..., ...}
            extracted = dep_data.get("data", None)
            if extracted is None:
                # calculate 任务的结果直接就是数据
                extracted = dep_data

            if not isinstance(extracted, dict):
                continue

            # 展平一层嵌套（LLM 可能返回 {"公司名": {...}} 或 {"2024": {...}}）
            flat_data = {}
            for k, v in extracted.items():
                if k in ("found", "success", "summary", "error", "confidence",
                         "expression", "display_name", "category", "unit"):
                    continue
                if isinstance(v, dict) and not isinstance(v, list):
                    # 嵌套结构：展平内层键值对
                    for sub_k, sub_v in v.items():
                        if not isinstance(sub_v, (dict, list)):
                            flat_data[sub_k] = sub_v
                elif not isinstance(v, (dict, list)):
                    flat_data[k] = v

            # 合并展平数据 + 顶层标量数据
            all_extracted = {**flat_data, **{k: v for k, v in extracted.items()
                                              if not isinstance(v, (dict, list))}}

            # 委托 ParamInjector 做三层回退注入（V3.0 升级）
            injector.inject(all_extracted, params)

            # 特殊处理：dupont 公式需要 4 个参数
            if task.params.get("formula") == "dupont":
                for needed in ("net_profit", "revenue", "total_assets", "equity"):
                    if needed not in params:
                        logger.warning(
                            f"杜邦分析缺少参数: {needed}，"
                            f"extracted keys: {list(all_extracted.keys())[:15]}，"
                            f"flat keys: {list(flat_data.keys())[:10]}"
                        )

        return params


class Executor:
    """
    执行器：按依赖顺序执行子任务列表。

    V2.5 MVP：线性执行（按 task_id 顺序）
    V3.0 增强：DAG 拓扑排序 + 并行执行同层任务
    """

    def __init__(self, tool_registry: ToolRegistry):
        self.tools = tool_registry

    def execute(self, tasks: List[AnalysisTask]) -> List[TaskResult]:
        """
        按顺序执行所有任务。

        流程：
        1. 按 task_id 排序
        2. 依次执行
        3. 失败的任务不阻塞后续任务，但标记依赖它的任务为失败

        返回:
            List[TaskResult]
        """
        # 按 task_id 排序
        sorted_tasks = sorted(tasks, key=lambda t: int(t.task_id) if t.task_id.isdigit() else 0)

        results: List[TaskResult] = []

        for task in sorted_tasks:
            # 检查依赖是否都已成功
            dep_failed = False
            for dep_id in task.depends_on:
                dep_result = next((r for r in results if r.task_id == dep_id), None)
                if dep_result and not dep_result.success:
                    dep_failed = True
                    break

            if dep_failed:
                results.append(TaskResult(
                    task_id=task.task_id,
                    task_type=task.task_type,
                    success=False,
                    summary="",
                    error=f"前置任务失败，跳过「{task.description}」",
                ))
                continue

            # 标记为运行中
            task.status = "running"

            # 执行
            result = self.tools.execute_task(task, results)
            task.status = "completed" if result.success else "failed"
            results.append(result)

            logger.info(
                f"任务 [{task.task_id}/{len(sorted_tasks)}] {task.status}: {task.description}"
            )

        return results
