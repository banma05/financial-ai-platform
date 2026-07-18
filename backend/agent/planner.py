"""
Planner（任务拆解器）— 将用户分析需求拆解为可执行的子任务列表

两种模式：
1. LLM 拆解：将自然语言需求解析为结构化任务列表
2. 模板加载：使用预设分析模板（杜邦/现金流/盈利评估）
"""
import json
from typing import List, Optional
from loguru import logger

from rag.model_router import chat, TaskType, LLM_MODEL, AGENT_LLM_MODEL
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
            {"task_id": "7", "task_type": "rag_context",
             "description": "从年报中检索盈利能力相关解读",
             "params": {"query": "{company} 毛利率 净利率 盈利能力 原因分析"}},
            {"task_id": "8", "task_type": "analyze",
             "description": "综合分析盈利能力并给出结论（引用原文）",
             "params": {},
             "depends_on": ["3", "4", "5", "7"]},
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
    "cash_flow": {
        "name": "cash_flow",
        "display_name": "现金流分析",
        "description": "分析经营活动/投资活动/筹资活动三大现金流，评估自由现金流和利润质量",
        "category": "现金流",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询经营活动现金流净额和净利润数据",
             "params": {"query": "{company} 经营活动产生的现金流量净额 净利润"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询投资活动和筹资活动现金流数据",
             "params": {"query": "{company} 投资活动产生的现金流量净额 筹资活动产生的现金流量净额 资本支出"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算自由现金流 FCF",
             "params": {"formula": "free_cash_flow"},
             "depends_on": ["1", "2"]},
            {"task_id": "4", "task_type": "calculate",
             "description": "计算经营现金流/净利润比率，评估利润质量",
             "params": {"formula": "cf_to_net_profit"},
             "depends_on": ["1"]},
            {"task_id": "5", "task_type": "chart",
             "description": "三大现金流结构柱状图",
             "params": {"chart_type": "bar", "title": "{company} 现金流结构分析"},
             "depends_on": ["1", "2"]},
            {"task_id": "6", "task_type": "analyze",
             "description": "综合评估现金流健康状况和利润质量",
             "params": {},
             "depends_on": ["3", "4"]},
        ],
    },
    "risk_scan": {
        "name": "risk_scan",
        "display_name": "财务风险扫描",
        "description": "从杠杆水平、流动性、偿债能力三个维度综合评估财务风险",
        "category": "风险分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询资产负债和流动性数据",
             "params": {"query": "{company} 总资产 总负债 流动资产 流动负债 存货"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询盈利和偿债能力数据",
             "params": {"query": "{company} 净利润 净资产 EBIT 利息费用 财务费用"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算资产负债率（杠杆水平）",
             "params": {"formula": "debt_ratio"},
             "depends_on": ["1"]},
            {"task_id": "4", "task_type": "calculate",
             "description": "计算流动比率（短期偿债）",
             "params": {"formula": "current_ratio"},
             "depends_on": ["1"]},
            {"task_id": "5", "task_type": "calculate",
             "description": "计算速动比率（严格流动性）",
             "params": {"formula": "quick_ratio"},
             "depends_on": ["1"]},
            {"task_id": "6", "task_type": "calculate",
             "description": "计算利息保障倍数（长期偿债）",
             "params": {"formula": "interest_coverage"},
             "depends_on": ["2"]},
            {"task_id": "7", "task_type": "chart",
             "description": "风险指标雷达图",
             "params": {"chart_type": "radar", "title": "{company} 财务风险雷达图"},
             "depends_on": ["3", "4", "5", "6"]},
            {"task_id": "8", "task_type": "analyze",
             "description": "综合评估财务风险等级并给出预警建议",
             "params": {},
             "depends_on": ["3", "4", "5", "6"]},
        ],
    },
    # ── V6.0 新增模板 ──
    "cross_company_profit": {
        "name": "cross_company_profit",
        "display_name": "跨公司盈利对比",
        "description": "对比两家公司的核心盈利指标（毛利率/净利率/ROE/ROA）并可视化差异",
        "category": "对比分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询公司A的盈利数据",
             "params": {"query": "{company_a} 营业收入 营业成本 净利润 净资产 总资产"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询公司B的盈利数据",
             "params": {"query": "{company_b} 营业收入 营业成本 净利润 净资产 总资产"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算公式A的毛利率、净利率、ROE、ROA",
             "params": {"formula": "gross_profit_margin,net_profit_margin,roe,roa"},
             "depends_on": ["1"]},
            {"task_id": "4", "task_type": "calculate",
             "description": "计算公式B的毛利率、净利率、ROE、ROA",
             "params": {"formula": "gross_profit_margin,net_profit_margin,roe,roa"},
             "depends_on": ["2"]},
            {"task_id": "5", "task_type": "chart",
             "description": "两公司盈利指标对比柱状图",
             "params": {"chart_type": "bar", "title": "盈利能力对比"},
             "depends_on": ["3", "4"]},
            {"task_id": "6", "task_type": "analyze",
             "description": "对比两公司盈利能力差异并给出投资建议",
             "params": {},
             "depends_on": ["3", "4"]},
        ],
    },
    "multi_dimension": {
        "name": "multi_dimension",
        "display_name": "多维度综合分析",
        "description": "从盈利/成长/偿债/营运四个维度全面评估公司财务健康状况",
        "category": "综合分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询盈利相关数据",
             "params": {"query": "{company} 营业收入 营业成本 净利润 净资产 总资产"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询资产负债和现金流数据",
             "params": {"query": "{company} 总负债 流动资产 流动负债 存货 经营活动产生的现金流量净额"}},
            {"task_id": "3", "task_type": "data_query",
             "description": "查询历史对比数据",
             "params": {"query": "{company} 去年 营业收入 净利润 总资产"}},
            {"task_id": "4", "task_type": "calculate",
             "description": "盈利维度：毛利率、净利率、ROE",
             "params": {"formula": "gross_profit_margin,net_profit_margin,roe"},
             "depends_on": ["1"]},
            {"task_id": "5", "task_type": "calculate",
             "description": "偿债维度：资产负债率、流动比率",
             "params": {"formula": "debt_ratio,current_ratio"},
             "depends_on": ["1", "2"]},
            {"task_id": "6", "task_type": "calculate",
             "description": "运营维度：总资产周转率",
             "params": {"formula": "total_asset_turnover"},
             "depends_on": ["1"]},
            {"task_id": "7", "task_type": "calculate",
             "description": "成长维度：营收增长率、净利润增长率",
             "params": {"formula": "revenue_growth,net_profit_growth"},
             "depends_on": ["1", "3"]},
            {"task_id": "8", "task_type": "chart",
             "description": "四维度综合雷达图",
             "params": {"chart_type": "radar", "title": "{company} 四维度财务健康雷达图"},
             "depends_on": ["4", "5", "6", "7"]},
            {"task_id": "9", "task_type": "analyze",
             "description": "基于四维度结果综合评估财务健康状况",
             "params": {},
             "depends_on": ["4", "5", "6", "7"]},
        ],
    },
}


class Planner:
    """
    分析需求 → 子任务列表（AnalysisPlan）

    V6.0 流程（模板匹配优先）：
    1. 检查是否指定了分析模板 → 有则加载预设任务
    2. 关键词匹配已有模板 → 有则直接走模板（跳过 LLM，0.1s vs 36s）
    3. 否则用 LLM 解析用户输入，生成任务列表
    4. 检测是否有歧义 → 需要追问时返回 clarification_question
    """

    # 触发使用 pro 模型的复杂查询关键词
    _COMPLEX_PATTERNS = [
        "对比", "差异", "维度", "综合", "全面", "三家", "两家", "多公司",
        "跨公司", "横向", "纵向", "深度", "详细", "系统性",
    ]

    def __init__(self):
        pass  # 无状态，LLM调用直接走 chat()

    def _is_complex(self, user_input: str) -> bool:
        """检测是否为复杂查询（需要 pro 模型拆解）"""
        companies = ["茅台", "比亚迪", "五粮液", "宁德", "美的", "恒瑞", "招行", "平安", "汾酒", "泸州老窖", "洋河", "伊利", "格力", "海康", "讯飞"]
        company_count = sum(1 for c in companies if c in user_input)
        if company_count >= 2:
            return True
        if any(kw in user_input for kw in self._COMPLEX_PATTERNS):
            return True
        if len(user_input) >= 60:
            return True
        return False

    def plan(self, user_input: str, template_name: Optional[str] = None) -> AnalysisPlan:
        """
        入口方法：将用户输入转为执行计划。

        V6.0 升级：模板匹配优先——关键词命中模板时直接走模板，
        跳过 LLM 拆解（0.1s vs 36s），大幅降低 hard 题延迟。

        参数:
            user_input: 用户分析需求
            template_name: 可选模板名（"profitability"/"dupont"/"growth"）

        返回:
            AnalysisPlan(tasks=[...], requires_clarification=None或追问内容)
        """
        # 模式 1：显式指定模板
        if template_name and template_name in BUILTIN_TEMPLATES:
            logger.info(f"使用分析模板（显式）: {template_name}")
            plan = self._load_template(template_name, user_input)
        # ── V6.0: 模式 2：关键词匹配模板（跳过 LLM，0.1s vs 36s）──
        elif self._match_template(user_input):
            matched = self._match_template(user_input)
            logger.info(f"使用分析模板（匹配）: {matched}")
            plan = self._load_template(matched, user_input)
        else:
            # 模式 3：自由分析（LLM 拆解）
            logger.info("LLM 自由拆解模式")
            plan = self._parse_with_llm(user_input)

        # V8.3: 兜底——有数据但无图表的计划，强制注入图表
        return self._ensure_chart(plan, user_input)

    def _ensure_chart(self, plan: "AnalysisPlan", user_input: str) -> "AnalysisPlan":
        """
        V8.3: 任何有 data_query 但无 chart 的计划，自动注入图表。

        图表只依赖数据查询（不依赖计算），确保计算部分失败时仍能出图。
        """
        tasks = plan.tasks
        data_tasks = [t for t in tasks if t.task_type == "data_query"]
        has_chart = any(t.task_type == "chart" for t in tasks)

        if data_tasks and not has_chart:
            # 依赖所有数据查询任务（计算失败不影响图表生成）
            data_ids = [t.task_id for t in data_tasks]
            chart_task = AnalysisTask(
                task_id=str(len(tasks) + 1),
                task_type="chart",
                description="生成数据可视化图表",
                params={"chart_type": "bar"},
                depends_on=data_ids,
            )
            tasks.append(chart_task)
            logger.info(f"[Planner] 自动注入图表任务: task_id={chart_task.task_id}, depends_on={data_ids}")

        # 已有 chart 但依赖了 calc 任务 → 也加上 data 依赖
        for t in tasks:
            if t.task_type == "chart":
                for dt in data_tasks:
                    if dt.task_id not in t.depends_on:
                        t.depends_on.append(dt.task_id)

        return plan

    def _match_template(self, user_input: str) -> Optional[str]:
        """
        基于关键词匹配预设模板（V6.0 新增）。

        匹配规则（按优先级，命中第一个即返回）：
        1. 多公司对比关键词 → cross_company_profit
        2. 多维度/全面/综合关键词 → multi_dimension
        3. 杜邦/ROE分解 → dupont
        4. 现金流/FCF → cash_flow
        5. 风险/杠杆/偿债 → risk_scan
        6. 成长/增长 → growth
        7. 盈利/毛利率/净利率 → profitability

        返回模板名或 None。
        """
        companies = ["茅台", "比亚迪", "五粮液", "宁德", "美的", "恒瑞", "招行", "平安", "汾酒", "泸州老窖", "洋河", "伊利", "格力", "海康", "讯飞"]
        company_count = sum(1 for c in companies if c in user_input)

        contrast_kw = ["对比", "比较", "差异", "哪个更", "哪家更", "较量"]
        profit_kw = ["盈利", "利润", "毛利", "净利", "赚钱", "回报"]

        # 多公司对比 → cross_company_profit
        if company_count >= 2 and any(kw in user_input for kw in contrast_kw):
            return "cross_company_profit"
        if company_count >= 2 and any(kw in user_input for kw in profit_kw):
            return "cross_company_profit"

        # 多维度关键词 → multi_dimension
        multi_kw = ["全面评估", "综合分析", "多维度", "多维分析", "全方位",
                     "系统性评估", "财务健康", "整体财务", "综合财务", "全面分析"]
        if any(kw in user_input for kw in multi_kw):
            return "multi_dimension"

        # 杜邦关键词 → dupont
        if any(kw in user_input for kw in ["杜邦", "ROE分解", "三因子", "权益乘数"]):
            return "dupont"

        # 现金流关键词 → cash_flow
        if any(kw in user_input for kw in ["现金流", "FCF", "自由现金流", "利润质量"]) and company_count >= 1:
            return "cash_flow"

        # 风险关键词 → risk_scan
        if any(kw in user_input for kw in ["风险", "杠杆", "偿债", "预警", "风险扫描", "债务风险"]):
            return "risk_scan"

        # 成长关键词 → growth
        if any(kw in user_input for kw in ["成长", "增长趋势", "增长率", "发展速度", "成长性"]):
            return "growth"

        # 盈利关键词（最宽泛，放最后）→ profitability
        if any(kw in user_input for kw in profit_kw):
            return "profitability"

        return None

    def _load_template(self, template_name: str, user_input: str) -> AnalysisPlan:
        """从模板库加载预设任务，替换 {company}/{company_a}/{company_b} 占位符"""
        template = BUILTIN_TEMPLATES[template_name]

        # 尝试从用户输入中提取公司名
        company = user_input

        # 多公司模板：提取公司A和公司B
        company_a = company_b = user_input
        known_companies = ["茅台", "比亚迪", "腾讯", "五粮液", "宁德", "阿里", "京东", "美团"]
        found = [c for c in known_companies if c in user_input]
        if len(found) >= 2:
            company_a = found[0]
            company_b = found[1]
        elif len(found) == 1:
            company_a = company_b = found[0]

        tasks = []
        for t in template["tasks"]:
            desc = t["description"].replace("{company}", company)
            desc = desc.replace("{company_a}", company_a).replace("{company_b}", company_b)
            params = {}
            for k, v in t["params"].items():
                if isinstance(v, str):
                    v = v.replace("{company}", company)
                    v = v.replace("{company_a}", company_a).replace("{company_b}", company_b)
                params[k] = v
            tasks.append(AnalysisTask(
                task_id=t["task_id"],
                task_type=t["task_type"],
                description=desc,
                params=params,
                depends_on=t.get("depends_on", []),
            ))

        return AnalysisPlan(tasks=tasks)

    def _parse_with_llm(self, user_input: str) -> AnalysisPlan:
        """LLM 拆解用户分析需求为子任务列表"""
        prompt = f"""你是一个财务分析任务拆解专家。请将用户的分析需求拆解为可执行的子任务。

## 用户需求
{user_input}

## 可用任务类型
- data_query: 从知识库查询财务数字（参数：query=查询内容）→ 返回结构化数值
- rag_context: 从知识库检索文字解读和原因分析（参数：query=查询内容）→ 返回原文引用段落
- calculate: 财务指标计算（参数：formula=公式名, 注：公式名见下方）
- chart: 生成可视化图表（参数：chart_type=图表类型[line/bar/pie/radar/dual_axis], title=图表标题）
- analyze: 综合分析并生成结论
- compare: 对比分析（需要先做多个 data_query）
# MCP外部工具（6种，用于获取实时/外部数据）：
# ⚠️ mcp_financial_statements 返回原始财报科目名（如"少数股东权益"），会与 SQL 精确数据冲突导致计算错误。
#    财务指标查询（营收/利润/资产/现金流）只用 data_query！mcp_financial_statements 不要用！
#    MCP 仅用于：实时股价(mcp_stock_price)、行业对比(mcp_industry_comparison)、大盘指数(mcp_market_index)、财报日历(mcp_financial_calendar)
- mcp_stock_price / mcp_financial_statements / mcp_calculate_ratio / mcp_industry_comparison / mcp_market_index / mcp_financial_calendar

## 可用财务公式（共 19 个）
# 盈利能力
- gross_profit_margin: 毛利率 (revenue, cost)
- net_profit_margin: 净利率 (net_profit, revenue)
- roe: ROE净资产收益率 (net_profit, avg_equity)
- roa: ROA总资产收益率 (net_profit, avg_total_assets)
- ebitda_margin: EBITDA率 (ebitda, revenue)
# 偿债能力
- debt_ratio: 资产负债率 (total_liabilities, total_assets)
- current_ratio: 流动比率 (current_assets, current_liabilities)
- quick_ratio: 速动比率 (current_assets, inventory, current_liabilities)
- interest_coverage: 利息保障倍数 (ebit, interest_expense)
# 营运能力
- inventory_turnover: 存货周转率 (cost, avg_inventory)
- receivable_turnover: 应收周转率 (revenue, avg_receivables)
- total_asset_turnover: 总资产周转率 (revenue, avg_total_assets)
# 成长能力
- revenue_growth: 营收增长率 (current_revenue, previous_revenue)
- net_profit_growth: 净利润增长率 (current_profit, previous_profit)
# 估值指标
- pe_ratio: 市盈率 (stock_price, eps)
- pb_ratio: 市净率 (stock_price, bvps)
# 现金流
- free_cash_flow: 自由现金流 (operating_cf, capital_expenditure)
- cf_to_net_profit: 经营现金流/净利润比率 (operating_cf, net_profit)
# 综合分析
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
8. 任务数量控制在 2-6 个。**任何涉及数字对比或多指标的查询，都必须包含一个 chart 任务。** 包含"增长/变化/趋势/对比/同比/环比"等关键词时必须加 chart。简单查询（单公司单年单指标）至少 2 个任务（data_query + analyze），复杂查询最多 6 个

## ⚠️ 参数精确性铁律（违反则任务执行失败）
1. **formula 必须严格从上方"可用财务公式"列表中选取**，一字不差。需要多个公式时用逗号分隔："roe,net_profit_margin,gross_profit_margin"
2. **MCP 工具参数键名必须精确**。mcp_industry_comparison 的 sector 参数只能是 "白酒"/"新能源"/"互联网" 三个值
3. **chart_type 只能是** line/bar/pie/radar/dual_axis 五个值，不要自创
4. **depends_on 使用 task_id 字符串列表**，不要用数字

## ❌ 常见错误（千万不要犯）
- ❌ `"formula": "毛利率"` → 应该用 `"formula": "gross_profit_margin"`
- ❌ `"formula": "ROE"` → 应该用 `"formula": "roe"`
- ❌ `"params": {{"sector": "科技"}}` → sector 只能是 白酒/新能源/互联网
- ❌ `"params": {{"chart_type": "柱状图"}}` → 应该用 `"chart_type": "bar"`
- ❌ `"formula": ["roe", "net_profit_margin"]` → 应该用 `"formula": "roe,net_profit_margin"`
"""

        # 🔧 复杂查询用 pro 保质量，简单查询用 flash 提速
        # 硬题 flash 频繁 JSON 空返回（浪费 20s+ 再切 pro），不值得
        task_type = TaskType.COMPLEX if self._is_complex(user_input) else TaskType.SIMPLE
        messages = [{"role": "user", "content": prompt}]

        plan_dict = self._try_llm_parse(messages, user_input, task_type)
        if plan_dict is None and task_type == TaskType.SIMPLE:
            # 仅 flash 解析失败时切 pro（JSON 格式错误，不是空返回）
            logger.warning("Flash 拆解失败，重试 pro 模型...")
            plan_dict = self._try_llm_parse(messages, user_input, TaskType.COMPLEX)

        if plan_dict is None:
            logger.warning("LLM 拆解彻底失败，回退为单任务直接分析")
            fallback_tasks = [
                AnalysisTask(task_id="1", task_type="data_query",
                             description=f"查询与「{user_input}」相关的财务数据",
                             params={"query": user_input}),
                AnalysisTask(task_id="2", task_type="analyze",
                             description=f"基于查询结果分析「{user_input}」",
                             params={}, depends_on=["1"]),
            ]
            return AnalysisPlan(tasks=fallback_tasks)

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

    def _try_llm_parse(self, messages, user_input, task_type):
        """尝试 LLM 拆解，失败返回 None（不抛异常）"""
        model_hint = "pro" if task_type == TaskType.COMPLEX else "flash"
        logger.info(f"LLM 自由拆解模式（{model_hint}）")
        try:
            from utils.text import parse_llm_json
            text = chat(messages, query=user_input, task_type=task_type)
            return parse_llm_json(text)
        except Exception as e:
            logger.warning(f"LLM 拆解失败({model_hint}): {type(e).__name__}: {str(e)[:80]}")
            return None

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
