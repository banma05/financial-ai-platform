"""
Planner（任务拆解器）— 将用户分析需求拆解为可执行的子任务列表

两种模式：
1. LLM 拆解：将自然语言需求解析为结构化任务列表
2. 模板加载：使用预设分析模板（杜邦/现金流/盈利评估）
"""
import json
from typing import List, Optional
from loguru import logger

from rag.model_router import get_langchain_llm
from .schemas import AnalysisTask, AnalysisPlan


# ==================== 预设分析模板（V2.5 内置三个基础模板）====================

BUILTIN_TEMPLATES = {
    "profitability": {
        "name": "profitability",
        "display_name": "盈利能力评估",
        "description": "分析公司的毛利率、净利率、ROE、ROA 等核心盈利指标",
        "category": "综合分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询营业收入、营业成本数据",
             "params": {"query": "{company} 营业收入 营业成本"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询净利润、净资产、总资产数据",
             "params": {"query": "{company} 净利润 净资产 总资产"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算毛利率",
             "params": {"formula": "gross_profit_margin"},
             "depends_on": ["1"]},
            {"task_id": "4", "task_type": "calculate",
             "description": "计算净利率",
             "params": {"formula": "net_profit_margin"},
             "depends_on": ["1", "2"]},
            {"task_id": "5", "task_type": "calculate",
             "description": "计算 ROE 和 ROA",
             "params": {"formula": "roe"},
             "depends_on": ["2"]},
            {"task_id": "6", "task_type": "chart",
             "description": "盈利能力指标柱状图",
             "params": {"chart_type": "bar"},
             "depends_on": ["3", "4", "5"]},
            {"task_id": "7", "task_type": "analyze",
             "description": "综合分析盈利能力并给出结论",
             "params": {},
             "depends_on": ["3", "4", "5"]},
        ],
    },
    "dupont": {
        "name": "dupont",
        "display_name": "杜邦分析",
        "description": "通过 ROE 三因子分解（净利率 × 资产周转率 × 权益乘数）分析盈利能力驱动因素",
        "category": "综合分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询净利润、营业收入、总资产、净资产",
             "params": {"query": "{company} 净利润 营业收入 总资产 净资产"}},
            {"task_id": "2", "task_type": "calculate",
             "description": "执行杜邦三因子分解",
             "params": {"formula": "dupont"},
             "depends_on": ["1"]},
            {"task_id": "3", "task_type": "chart",
             "description": "杜邦分析因子柱状图",
             "params": {"chart_type": "bar"},
             "depends_on": ["2"]},
            {"task_id": "4", "task_type": "analyze",
             "description": "分析 ROE 驱动因素，给出改善建议",
             "params": {},
             "depends_on": ["2"]},
        ],
    },
    "growth": {
        "name": "growth",
        "display_name": "成长性分析",
        "description": "分析营收增长率、净利润增长率、总资产增长率等成长指标",
        "category": "综合分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询近三年营收数据",
             "params": {"query": "{company} 2022年 2023年 2024年 营业收入"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询近三年净利润数据",
             "params": {"query": "{company} 2022年 2023年 2024年 净利润"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算营收增长率",
             "params": {"formula": "revenue_growth"},
             "depends_on": ["1"]},
            {"task_id": "4", "task_type": "calculate",
             "description": "计算净利润增长率",
             "params": {"formula": "net_profit_growth"},
             "depends_on": ["2"]},
            {"task_id": "5", "task_type": "chart",
             "description": "营收+净利趋势双轴图",
             "params": {"chart_type": "dual_axis"},
             "depends_on": ["1", "2", "3", "4"]},
            {"task_id": "6", "task_type": "analyze",
             "description": "分析增长趋势并给出可持续性评估",
             "params": {},
             "depends_on": ["3", "4"]},
        ],
    },
}


class Planner:
    """
    分析需求 → 子任务列表（AnalysisPlan）

    流程：
    1. 检查是否指定了分析模板 → 有则加载预设任务
    2. 否则用 LLM 解析用户输入，生成任务列表
    3. 检测是否有歧义 → 需要追问时返回 clarification_question
    """

    def __init__(self, llm=None):
        self.llm = llm or get_langchain_llm()

    def plan(self, user_input: str, template_name: Optional[str] = None) -> AnalysisPlan:
        """
        入口方法：将用户输入转为执行计划。

        参数:
            user_input: 用户分析需求
            template_name: 可选模板名（"profitability"/"dupont"/"growth"）

        返回:
            AnalysisPlan(tasks=[...], requires_clarification=None或追问内容)
        """
        # 模式 1：模板分析
        if template_name and template_name in BUILTIN_TEMPLATES:
            logger.info(f"使用分析模板: {template_name}")
            return self._load_template(template_name, user_input)

        # 模式 2：自由分析（LLM 拆解）
        logger.info("LLM 自由拆解模式")
        return self._parse_with_llm(user_input)

    def _load_template(self, template_name: str, user_input: str) -> AnalysisPlan:
        """从模板库加载预设任务，替换 {company} 占位符"""
        template = BUILTIN_TEMPLATES[template_name]

        # 尝试从用户输入中提取公司名（简单规则）
        company = user_input  # 默认用整个输入；后续 entity_router 会处理

        tasks = []
        for t in template["tasks"]:
            tasks.append(AnalysisTask(
                task_id=t["task_id"],
                task_type=t["task_type"],
                description=t["description"].replace("{company}", company),
                params={
                    k: v.replace("{company}", company) if isinstance(v, str) else v
                    for k, v in t["params"].items()
                },
                depends_on=t.get("depends_on", []),
            ))

        return AnalysisPlan(tasks=tasks)

    def _parse_with_llm(self, user_input: str) -> AnalysisPlan:
        """LLM 拆解用户分析需求为子任务列表"""
        prompt = f"""你是一个财务分析任务拆解专家。请将用户的分析需求拆解为可执行的子任务。

## 用户需求
{user_input}

## 可用任务类型
- data_query: 从知识库查询财务数据（参数：query=查询内容）
- calculate: 财务指标计算（参数：formula=公式名, 注：公式名见下方）
- chart: 生成可视化图表（参数：chart_type=图表类型[line/bar/pie/radar/dual_axis], title=图表标题）
- analyze: 综合分析并生成结论
- compare: 对比分析（需要先做多个 data_query）

## 可用财务公式
- gross_profit_margin: 毛利率 (revenue, cost)
- net_profit_margin: 净利率 (net_profit, revenue)
- roe: ROE净资产收益率 (net_profit, avg_equity)
- roa: ROA总资产收益率 (net_profit, avg_total_assets)
- debt_ratio: 资产负债率 (total_liabilities, total_assets)
- current_ratio: 流动比率 (current_assets, current_liabilities)
- revenue_growth: 营收增长率 (current_revenue, previous_revenue)
- net_profit_growth: 净利润增长率 (current_profit, previous_profit)
- free_cash_flow: 自由现金流 (operating_cf, capital_expenditure)
- dupont: 杜邦分析 (net_profit, revenue, total_assets, equity)

## 输出格式（严格 JSON，不要多余文字）
{{
  "tasks": [
    {{
      "task_id": "1",
      "task_type": "data_query",
      "description": "查询茅台2024年营业收入和营业成本",
      "params": {{"query": "贵州茅台 2024年 营业收入 营业成本"}},
      "depends_on": []
    }},
    {{
      "task_id": "2",
      "task_type": "calculate",
      "description": "计算毛利率",
      "params": {{"formula": "gross_profit_margin"}},
      "depends_on": ["1"]
    }}
  ],
  "requires_clarification": null
}}

## 规则
1. task_id 从 "1" 开始递增
2. 独立的数据查询可以并行（depends_on 为空）
3. 计算任务必须依赖对应的数据查询任务
4. 图表任务依赖对应的数据查询或计算任务
5. analyze 任务通常放在最后
6. 如果用户没有指定具体公司或年份，requires_clarification 设为需要追问的问题
7. 如果需求足够明确，requires_clarification 设为 null
8. 任务数量控制在 3-7 个，不要过度拆分
"""

        try:
            response = self.llm.invoke(prompt)
            # 提取 JSON
            text = response.content if hasattr(response, "content") else str(response)
            text = text.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            plan_dict = json.loads(text)

            tasks = []
            for t in plan_dict.get("tasks", []):
                tasks.append(AnalysisTask(
                    task_id=str(t["task_id"]),
                    task_type=t.get("task_type", "data_query"),
                    description=t.get("description", ""),
                    params=t.get("params", {}),
                    depends_on=t.get("depends_on", []),
                ))

            clarification = plan_dict.get("requires_clarification")
            return AnalysisPlan(tasks=tasks, requires_clarification=clarification)

        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            logger.warning(f"LLM 任务拆解失败: {e}，回退为单任务直接分析")
            # 回退：创建一个简单的 data_query + analyze 任务对
            fallback_tasks = [
                AnalysisTask(
                    task_id="1", task_type="data_query",
                    description=f"查询与「{user_input}」相关的财务数据",
                    params={"query": user_input},
                ),
                AnalysisTask(
                    task_id="2", task_type="analyze",
                    description=f"基于查询结果分析「{user_input}」",
                    params={},
                    depends_on=["1"],
                ),
            ]
            return AnalysisPlan(tasks=fallback_tasks)

    def _detect_ambiguity(self, user_input: str) -> Optional[str]:
        """检测是否需要追问（简单规则版，V3.0 升级为 LLM 判断）"""
        has_company = any(kw in user_input for kw in ["茅台", "比亚迪", "腾讯", "五粮液", "宁德", "阿里", "京东"])
        has_year = any(kw in user_input for kw in ["2024", "2023", "2022", "2021", "去年", "今年", "近三年", "近几年"])
        has_indicator = any(kw in user_input for kw in [
            "毛利率", "净利率", "ROE", "营收", "净利润", "现金流", "资产负债", "增长率", "杜邦"
        ])

        missing = []
        if not has_company:
            missing.append("需要分析哪家公司？")
        if not has_indicator:
            missing.append("需要分析哪些指标？")
        if not has_year:
            missing.append("需要分析哪个时间段？")

        return " ".join(missing) if missing else None
