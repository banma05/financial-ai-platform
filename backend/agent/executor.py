"""
Executor（工具执行编排器）+ ToolRegistry（工具注册中心）

职责：
1. ToolRegistry 管理所有可用工具（注册/查询/执行）
2. Executor 按依赖顺序执行子任务列表
3. 将前置任务的结果注入到后续任务参数中
"""
import re
from typing import List, Dict, Any, Callable
from loguru import logger

from .schemas import AnalysisTask, TaskResult

# ==================== 财务术语中→英映射表 ====================
# DataQuery 的 LLM 提取返回中文键名，但公式参数使用英文名
# 此映射在依赖注入时将中文键名转换为公式可识别的参数名

FINANCIAL_TERM_TO_PARAM: Dict[str, str] = {
    # 盈利能力
    "营业收入": "revenue", "营业总收入": "revenue", "营收": "revenue",
    "营业成本": "cost", "成本": "cost",
    "净利润": "net_profit", "归母净利润": "net_profit",
    "归属于母公司股东的净利润": "net_profit",
    "净资产": "equity", "股东权益": "equity",
    "平均净资产": "avg_equity", "净资产平均值": "avg_equity",
    "总资产": "total_assets", "资产总计": "total_assets",
    "平均总资产": "avg_total_assets", "总资产平均值": "avg_total_assets",
    "毛利润": "gross_profit",
    # 偿债能力
    "总负债": "total_liabilities", "负债合计": "total_liabilities",
    "流动资产": "current_assets", "流动资产合计": "current_assets",
    "流动负债": "current_liabilities", "流动负债合计": "current_liabilities",
    "存货": "inventory", "存货净额": "inventory",
    "利息费用": "interest_expense", "财务费用": "interest_expense",
    "EBIT": "ebit", "息税前利润": "ebit",
    # 现金流
    "经营活动现金流净额": "operating_cf",
    "经营活动产生的现金流量净额": "operating_cf",
    "经营活动现金流": "operating_cf",
    "投资活动现金流净额": "investing_cf",
    "投资活动产生的现金流量净额": "investing_cf",
    "投资活动现金流": "investing_cf",
    "筹资活动现金流净额": "financing_cf",
    "筹资活动产生的现金流量净额": "financing_cf",
    "筹资活动现金流": "financing_cf",
    "资本支出": "capital_expenditure",
    "购建固定资产无形资产和其他长期资产支付的现金": "capital_expenditure",
    # 估值
    "基本每股收益": "eps", "每股收益": "eps", "EPS": "eps",
    "股价": "stock_price", "股票价格": "stock_price",
    # 成长（跨年对比）
    "上期营业收入": "previous_revenue", "上期营收": "previous_revenue",
    "上期净利润": "previous_profit",
    "当期营业收入": "current_revenue", "当期营收": "current_revenue",
    "当期净利润": "current_profit",
    "营业收入_上期": "previous_revenue", "净利润_上期": "previous_profit",
    "营业收入_当期": "current_revenue", "净利润_当期": "current_profit",
    # 通用
    "EBITDA": "ebitda",
}

# 金额单位解析正则
_UNIT_PATTERN = re.compile(
    r'^(-?\d+\.?\d*)\s*(亿元|万元|元|亿|万|%|％)?$'
)

# 单位换算到「元」
_UNIT_TO_MULTIPLIER = {
    "亿元": 100_000_000, "亿": 100_000_000,
    "万元": 10_000, "万": 10_000,
    "元": 1,
    "%": 1, "％": 1,
}


def _parse_financial_value(value) -> float:
    """
    将财务数值字符串解析为 float。

    支持格式: "1709.90亿元" → 1709.90（保留原始数值，不换算到元）
    "91.5%" → 91.5
    已经是数字的直接返回
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    match = _UNIT_PATTERN.match(value.strip())
    if match:
        num = float(match.group(1))
        # 不进行单位换算，保留原始数值（财务分析中亿元就是亿元）
        # 百分比和比率已经是正确单位
        return num
    # 尝试直接转换数字字符串
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _map_chinese_to_param(chinese_key: str) -> str:
    """将中文财务术语映射为公式参数名，无匹配时返回原值"""
    return FINANCIAL_TERM_TO_PARAM.get(chinese_key, chinese_key)


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
        2. 将中文键名映射为公式参数名（如 营业收入→revenue）
        3. 解析带单位的字符串数值（如 "1709.90亿元"→1709.90）
        4. 合并到当前任务参数中（不覆盖已有参数）

        V2.5 增强版：中→英映射 + 单位解析
        V3.0 增强：LLM 辅助智能字段匹配
        """
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

            # 先处理展平后的数据
            all_extracted = {**flat_data, **{k: v for k, v in extracted.items()
                                              if not isinstance(v, (dict, list))}}

            # 遍历提取的数据，做中→英映射 + 数值解析
            for k, v in all_extracted.items():
                # 解析数值（支持 "1709.90亿元" 等带单位字符串）
                parsed = _parse_financial_value(v)
                if parsed is None:
                    continue

                # 中→英键名映射
                mapped_key = _map_chinese_to_param(k)

                # 注入：优先使用映射后的键名，不覆盖已有参数
                if mapped_key not in params:
                    params[mapped_key] = parsed

                # 同时保留原始键名（兜底）
                if k != mapped_key and k not in params:
                    params[k] = parsed

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
