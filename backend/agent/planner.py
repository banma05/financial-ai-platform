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
             "params": {"query": "{company} {year}年 营业收入 营业成本"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询净利润、净资产、总资产数据",
             "params": {"query": "{company} {year}年 净利润 净资产 总资产"}},
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
             "params": {"chart_type": "auto"},
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
             "params": {"query": "{company} {year}年 净利润 营业收入 总资产 净资产"}},
            {"task_id": "2", "task_type": "calculate",
             "description": "执行杜邦三因子分解",
             "params": {"formula": "dupont"},
             "depends_on": ["1"]},
            {"task_id": "3", "task_type": "rag_context",
             "description": "从年报中检索ROE驱动因素的定性解读",
             "params": {"query": "{company} ROE 净资产收益率 驱动因素 盈利能力 原因分析"}},
            {"task_id": "4", "task_type": "chart",
             "description": "杜邦分析因子柱状图",
             "params": {"chart_type": "auto"},
             "depends_on": ["2"]},
            {"task_id": "5", "task_type": "analyze",
             "description": "分析 ROE 驱动因素并给出改善建议（结合年报原文解读）",
             "params": {},
             "depends_on": ["2", "3"]},
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
             "params": {"query": "{company} {last_year}年 {year}年 营业收入"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询近三年净利润数据",
             "params": {"query": "{company} {last_year}年 {year}年 净利润"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算营收增长率",
             "params": {"formula": "revenue_growth"},
             "depends_on": ["1"]},
            {"task_id": "4", "task_type": "calculate",
             "description": "计算净利润增长率",
             "params": {"formula": "net_profit_growth"},
             "depends_on": ["2"]},
            {"task_id": "5", "task_type": "rag_context",
             "description": "从年报中检索增长驱动因素和管理层展望",
             "params": {"query": "{company} 营收增长 净利润增长 原因分析 发展前景 行业趋势"}},
            {"task_id": "6", "task_type": "chart",
             "description": "营收+净利趋势双轴图",
             "params": {"chart_type": "auto"},
             "depends_on": ["1", "2", "3", "4"]},
            {"task_id": "7", "task_type": "analyze",
             "description": "分析增长趋势并结合年报给出可持续性评估",
             "params": {},
             "depends_on": ["3", "4", "5"]},
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
             "params": {"query": "{company} {year}年 经营活动产生的现金流量净额 净利润"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询投资活动和筹资活动现金流数据",
             "params": {"query": "{company} {year}年 投资活动产生的现金流量净额 筹资活动产生的现金流量净额 资本支出"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算自由现金流 FCF",
             "params": {"formula": "free_cash_flow"},
             "depends_on": ["1", "2"]},
            {"task_id": "4", "task_type": "calculate",
             "description": "计算经营现金流/净利润比率，评估利润质量",
             "params": {"formula": "cf_to_net_profit"},
             "depends_on": ["1"]},
            {"task_id": "5", "task_type": "rag_context",
             "description": "从年报中检索现金流相关经营解读",
             "params": {"query": "{company} 现金流 经营现金流 利润质量 现金流健康度 资金状况"}},
            {"task_id": "6", "task_type": "chart",
             "description": "三大现金流结构柱状图",
             "params": {"chart_type": "auto", "title": "{company} 现金流结构分析"},
             "depends_on": ["1", "2"]},
            {"task_id": "7", "task_type": "analyze",
             "description": "综合评估现金流健康状况并结合年报给出资金管理建议",
             "params": {},
             "depends_on": ["3", "4", "5"]},
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
             "params": {"query": "{company} {year}年 总资产 总负债 流动资产 流动负债 存货"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询盈利和偿债能力数据",
             "params": {"query": "{company} {year}年 净利润 净资产 营业利润 利息费用 财务费用"}},
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
            {"task_id": "7", "task_type": "rag_context",
             "description": "从年报中检索风险因素和管理层应对措施",
             "params": {"query": "{company} 财务风险 偿债风险 流动性风险 经营风险 风险应对 管理层讨论"}},
            {"task_id": "8", "task_type": "chart",
             "description": "风险指标雷达图",
             "params": {"chart_type": "auto", "title": "{company} 财务风险指标"},
             "depends_on": ["3", "4", "5", "6"]},
            {"task_id": "9", "task_type": "analyze",
             "description": "综合评估财务风险等级并结合年报给出预警建议",
             "params": {},
             "depends_on": ["3", "4", "5", "6", "7"]},
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
             "params": {"query": "{company_a} {year}年 营业收入 营业成本 净利润 净资产 总资产"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询公司B的盈利数据",
             "params": {"query": "{company_b} {year}年 营业收入 营业成本 净利润 净资产 总资产"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算公式A的毛利率、净利率、ROE、ROA",
             "params": {"formula": "gross_profit_margin,net_profit_margin,roe,roa"},
             "depends_on": ["1"]},
            {"task_id": "4", "task_type": "calculate",
             "description": "计算公式B的毛利率、净利率、ROE、ROA",
             "params": {"formula": "gross_profit_margin,net_profit_margin,roe,roa"},
             "depends_on": ["2"]},
            {"task_id": "5", "task_type": "rag_context",
             "description": "从年报中检索两公司竞争优势和盈利能力差异的原因",
             "params": {"query": "{company_a} {company_b} 盈利能力对比 竞争优势 差异原因 商业模式 行业地位"}},
            {"task_id": "6", "task_type": "chart",
             "description": "两公司盈利指标对比柱状图",
             "params": {"chart_type": "auto", "title": "盈利能力对比"},
             "depends_on": ["3", "4"]},
            {"task_id": "7", "task_type": "analyze",
             "description": "对比两公司盈利能力差异，结合年报解读给出投资建议",
             "params": {},
             "depends_on": ["3", "4", "5"]},
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
             "params": {"query": "{company} {year}年 营业收入 营业成本 净利润 净资产 总资产"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询资产负债和现金流数据",
             "params": {"query": "{company} {year}年 总负债 流动资产 流动负债 存货 经营活动产生的现金流量净额"}},
            {"task_id": "3", "task_type": "data_query",
             "description": "查询历史对比数据",
             "params": {"query": "{company} {last_year}年 营业收入 净利润 总资产"}},
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
            {"task_id": "8", "task_type": "rag_context",
             "description": "从年报中检索四维度相关的管理层分析和经营策略",
             "params": {"query": "{company} 盈利能力 成长性 偿债能力 营运效率 管理层讨论 经营策略 行业分析"}},
            {"task_id": "9", "task_type": "chart",
             "description": "四维度指标对比柱状图",
             "params": {"chart_type": "auto", "title": "{company} 四维度财务指标"},
             "depends_on": ["4", "5", "6", "7"]},
            {"task_id": "10", "task_type": "analyze",
             "description": "基于四维度结果并结合年报解读综合评估财务健康状况",
             "params": {},
             "depends_on": ["4", "5", "6", "7", "8"]},
        ],
    },
    # ── V9.0 P1-4: 估值分析 ──
    "valuation": {
        "name": "valuation",
        "display_name": "估值分析",
        "description": "计算 PE/PB/PS 三大估值指标，结合历史分位和行业对比评估估值水平",
        "category": "估值分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询每股收益、每股净资产、营业收入数据",
             "params": {"query": "{company} {year}年 基本每股收益 净资产 营业收入 总股本"}},
            {"task_id": "2", "task_type": "mcp_stock_price",
             "description": "获取当前股价数据",
             "params": {"symbol": "", "target_date": "{year}-12-31"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算 PE、PB 估值指标",
             "params": {"formula": "pe_ratio,pb_ratio"},
             "depends_on": ["1", "2"]},
            {"task_id": "4", "task_type": "rag_context",
             "description": "从年报中检索估值相关讨论和行业估值水平",
             "params": {"query": "{company} 估值水平 市盈率 市净率 行业对比 投资价值"}},
            {"task_id": "5", "task_type": "chart",
             "description": "估值指标柱状图",
             "params": {"chart_type": "auto", "title": "{company} 估值指标"},
             "depends_on": ["3"]},
            {"task_id": "6", "task_type": "analyze",
             "description": "综合评估估值水平并结合年报给出投资建议",
             "params": {},
             "depends_on": ["3", "4"]},
        ],
    },
    # ── V9.0 P1-4: 营运能力 ──
    "operating": {
        "name": "operating",
        "display_name": "营运能力分析",
        "description": "分析存货周转率、应收账款周转率、总资产周转率等营运效率指标",
        "category": "营运分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询营收、成本、存货数据",
             "params": {"query": "{company} {year}年 {last_year}年 营业收入 营业成本 存货"}},
            {"task_id": "2", "task_type": "data_query",
             "description": "查询应收、总资产数据",
             "params": {"query": "{company} {year}年 {last_year}年 应收账款 总资产"}},
            {"task_id": "3", "task_type": "calculate",
             "description": "计算三大周转率",
             "params": {"formula": "inventory_turnover,receivable_turnover,total_asset_turnover"},
             "depends_on": ["1", "2"]},
            {"task_id": "4", "task_type": "rag_context",
             "description": "从年报中检索营运效率相关管理层讨论",
             "params": {"query": "{company} 存货周转 应收账款周转 营运效率 供应链管理 经营策略"}},
            {"task_id": "5", "task_type": "chart",
             "description": "营运效率指标柱状图",
             "params": {"chart_type": "auto", "title": "{company} 营运效率指标"},
             "depends_on": ["3"]},
            {"task_id": "6", "task_type": "analyze",
             "description": "综合评估营运效率并结合年报给出改善建议",
             "params": {},
             "depends_on": ["3", "4"]},
        ],
    },
    # ── V9.0 P1-4: 费用结构 ──
    "cost_analysis": {
        "name": "cost_analysis",
        "display_name": "费用结构分析",
        "description": "分析销售费用、管理费用、研发费用、财务费用四大期间费用的占比和趋势",
        "category": "费用分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询四大费用和营收数据",
             "params": {"query": "{company} {year}年 销售费用 管理费用 研发费用 财务费用 营业收入"}},
            {"task_id": "2", "task_type": "calculate",
             "description": "计算各费用率",
             "params": {"formula": "sales_expense_ratio,admin_expense_ratio,rd_expense_ratio,finance_expense_ratio"},
             "depends_on": ["1"]},
            {"task_id": "3", "task_type": "rag_context",
             "description": "从年报中检索费用变动原因和管理层降本增效措施",
             "params": {"query": "{company} 销售费用 管理费用 研发费用 费用控制 降本增效 成本管理"}},
            {"task_id": "4", "task_type": "chart",
             "description": "费用占比饼图",
             "params": {"chart_type": "auto", "title": "{company} 期间费用结构"},
             "depends_on": ["2"]},
            {"task_id": "5", "task_type": "analyze",
             "description": "分析费用结构合理性并结合年报评估费用控制效果",
             "params": {},
             "depends_on": ["2", "3"]},
        ],
    },
    # ── V9.0 P1-4: 行业对比 ──
    "industry_compare": {
        "name": "industry_compare",
        "display_name": "行业对比分析",
        "description": "将公司核心指标与行业均值对比，识别竞争优势和短板",
        "category": "对比分析",
        "tasks": [
            {"task_id": "1", "task_type": "data_query",
             "description": "查询公司核心盈利和风险指标",
             "params": {"query": "{company} {year}年 营业收入 营业成本 净利润 净资产 总资产 总负债 流动资产 流动负债"}},
            {"task_id": "2", "task_type": "calculate",
             "description": "计算核心对比指标",
             "params": {"formula": "gross_profit_margin,net_profit_margin,roe,debt_ratio,current_ratio"},
             "depends_on": ["1"]},
            {"task_id": "3", "task_type": "rag_context",
             "description": "从年报中检索公司行业地位和竞争格局分析",
             "params": {"query": "{company} 行业地位 竞争格局 市场份额 竞争优势 行业排名"}},
            {"task_id": "4", "task_type": "chart",
             "description": "公司与行业均值雷达对比图",
             "params": {"chart_type": "auto", "title": "{company} vs 行业均值"},
             "depends_on": ["2"]},
            {"task_id": "5", "task_type": "analyze",
             "description": "综合评估公司的行业竞争力并给出战略建议",
             "params": {},
             "depends_on": ["2", "3"]},
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

    def __init__(self):
        pass  # 无状态，LLM调用直接走 chat()

    def plan(self, user_input: str, template_name: Optional[str] = None) -> AnalysisPlan:
        """
        V8.4: 简化入口 — 显式模板 或 LLM 自由拆解（移除关键词匹配）。

        参数:
            user_input: 用户分析需求
            template_name: 可选模板名（"profitability"/"dupont"/"growth"）

        返回:
            AnalysisPlan(tasks=[...], requires_clarification=None或追问内容)
        """
        if template_name and template_name in BUILTIN_TEMPLATES:
            logger.info(f"使用分析模板（显式）: {template_name}")
            plan = self._load_template(template_name, user_input)
        else:
            logger.info("LLM 自由拆解模式")
            plan = self._parse_with_llm(user_input)

        return self._ensure_chart(plan, user_input)

    def _ensure_chart(self, plan: "AnalysisPlan", user_input: str) -> "AnalysisPlan":
        """
        V8.4: 智能图表注入。已有 chart → 不动；无 chart + 数据维度 ≥ 3 → 用 auto。
        """
        tasks = plan.tasks
        has_chart = any(t.task_type == "chart" for t in tasks)
        if has_chart:
            # V8.5: 保留模板明确指定的 chart_type（如 radar/line），
            # 仅当 chart_type 为空、未设置或为默认值 'bar' 时改为 auto
            for t in tasks:
                if t.task_type == "chart":
                    ct = t.params.get("chart_type")
                    if ct in (None, "", "bar"):
                        t.params["chart_type"] = "auto"
            return plan

        # P2-9: chart 优先依赖 calculate(中文display_name), 自由拆解无calculate时回退data_query
        calc_tasks = [t for t in tasks if t.task_type == "calculate"]
        data_tasks = [t for t in tasks if t.task_type == "data_query"]

        if calc_tasks:
            dep_ids = [t.task_id for t in calc_tasks]
            dep_label = f"{len(dep_ids)}个calculate"
        elif data_tasks:
            dep_ids = [t.task_id for t in data_tasks]
            dep_label = f"{len(dep_ids)}个data_query(回退)"
        else:
            return plan

        chart_task = AnalysisTask(
            task_id=str(len(tasks) + 1),
            task_type="chart",
            description="自动生成数据可视化图表",
            params={"chart_type": "auto"},
            depends_on=dep_ids,
        )
        tasks.append(chart_task)
        logger.info(f"[Planner] 智能注入图表 (依赖{dep_label})")

        return plan

    @staticmethod
    def _estimate_dimensions(data_tasks) -> int:
        """从 data_query 的 query 参数中估算数据维度数"""
        from agent.tools.param_injection import FINANCIAL_TERM_TO_PARAM
        combined = " ".join(t.params.get("query", "") for t in data_tasks)
        found = set()
        for term in FINANCIAL_TERM_TO_PARAM:
            if term in combined:
                found.add(term)
                if len(found) >= 3:
                    return 3
        return len(found)

    def _load_template(self, template_name: str, user_input: str) -> AnalysisPlan:
        """从模板库加载预设任务，替换 {company}/{year} 等占位符"""
        import re
        from datetime import datetime

        template = BUILTIN_TEMPLATES[template_name]

        # ── V9.0: 从用户输入提取公司名（动态从 COMPANY_ALIASES 读）──
        company = user_input
        company_a = company_b = user_input
        try:
            from db.financial_query import COMPANY_ALIASES
            known_companies = sorted(set(COMPANY_ALIASES.keys()))
        except Exception:
            known_companies = ["贵州茅台", "比亚迪", "宁德时代", "五粮液", "招商银行", "美的集团"]
        # 用 max(len) 取最长匹配——"贵州茅台"比"茅台"更精确，自动去子串冲突
        raw_matches = [c for c in known_companies if c in user_input]
        if len(raw_matches) <= 1:
            found = raw_matches
        else:
            best = max(raw_matches, key=len)
            found = [best] + [c for c in raw_matches if c != best and c not in best]
        if not raw_matches:
            found = []
        elif len(raw_matches) == 1:
            found = raw_matches
        else:
            # 最长匹配 = 最精确的公司名（如"贵州茅台"比"茅台"更精确）
            best = max(raw_matches, key=len)
            # 保留 best + 所有不是 best 子串的其他匹配（真正的不同公司）
            found = [best] + [c for c in raw_matches if c != best and c not in best]
        if len(found) >= 2:
            company_a = found[0]
            company_b = found[1]
        elif len(found) == 1:
            company = found[0]
            company_a = company_b = found[0]

        # ── V9.0: 从用户输入提取年份 ──
        year_matches = re.findall(r'(20\d{2})\s*年?', user_input)
        if year_matches:
            year = year_matches[0]  # 取第一个匹配的年份
            year_range = f"{year_matches[0]}-{year_matches[-1]}" if len(year_matches) > 1 else year_matches[0]
            last_year = str(int(year) - 1)
        else:
            current_year = datetime.now().year
            year = str(current_year - 1)  # 默认最近完整财年
            year_range = year
            last_year = str(current_year - 2)

        tasks = []
        for t in template["tasks"]:
            desc = t["description"].replace("{company}", company)
            desc = desc.replace("{company_a}", company_a).replace("{company_b}", company_b)
            desc = desc.replace("{year}", year).replace("{year_range}", year_range).replace("{last_year}", last_year)
            params = {}
            for k, v in t["params"].items():
                if isinstance(v, str):
                    v = v.replace("{company}", company)
                    v = v.replace("{company_a}", company_a).replace("{company_b}", company_b)
                    v = v.replace("{year}", year).replace("{year_range}", year_range).replace("{last_year}", last_year)
                params[k] = v
            # P1-5 S2修复: 估值模板的 mcp_stock_price 自动填充股票代码
            if t["task_type"] == "mcp_stock_price" and not params.get("symbol", "").strip():
                target_company = company_a if company_a != company_b else company
                # 从 COMPANY_ALIASES 查找股票代码
                from db.financial_query import COMPANY_ALIASES
                symbol = ""
                for alias in sorted(COMPANY_ALIASES, key=len, reverse=True):
                    if alias in target_company or target_company in alias:
                        symbol = COMPANY_ALIASES[alias]
                        break
                params["symbol"] = symbol
                if not symbol:
                    logger.warning(f"[模板] 估值分析无法找到 {target_company} 的股票代码")
            tasks.append(AnalysisTask(
                task_id=t["task_id"],
                task_type=t["task_type"],
                description=desc,
                params=params,
                depends_on=t.get("depends_on", []),
            ))

        return AnalysisPlan(tasks=tasks)

    def _parse_with_llm(self, user_input: str) -> AnalysisPlan:
        """LLM 拆解用户分析需求为子任务列表（V8.4: 动态上下文增强）"""
        from datetime import datetime
        current_year = datetime.now().year

        # 动态获取可分析的公司列表
        try:
            from db.financial_query import COMPANY_ALIASES
            company_names = sorted(set(COMPANY_ALIASES.keys()))
        except Exception:
            company_names = ["贵州茅台", "比亚迪", "宁德时代", "五粮液", "招商银行"]
        company_list = "、".join(company_names)

        prompt = f"""你是一个财务分析任务拆解专家。请根据用户需求，灵活拆解为可执行的子任务。

## 当前环境（动态生成）
当前年份: {current_year}
可分析公司（{len(company_names)}家）: {company_list}

## 用户需求
{user_input}

## 可用任务类型
- data_query: 从知识库查询财务数字（参数：query=查询内容）→ 返回结构化数值
- rag_context: 从知识库检索文字解读和原因分析（参数：query=查询内容）→ 返回原文引用段落
- calculate: 财务指标计算（参数：formula=公式名, 注：公式名见下方）
- chart: 生成可视化图表（参数：chart_type=图表类型[line/bar/pie/radar/dual_axis], title=图表标题）
  📊 选型指南：
  · line=趋势分析（多年数据对比、利率走势等）
  · bar=指标对比（同类指标横向比较，如各产品毛利率）
  · pie=结构分布（不超过6项，如业务板块收入占比）
  · radar=多维度综合评估（3个以上不同量纲指标，如四维度财务健康度）
  · dual_axis=双量纲组合（营收+增速、利润+利润率等需双Y轴的场景）
- analyze: 综合分析并生成结论
- compare: 对比分析（需要先做多个 data_query）
# MCP外部工具（6种，用于获取实时/外部数据）：
# ⚠️ 财务指标（营收/利润/资产/现金流/负债/费用）用 data_query（SQL精确数据）。
#    mcp_stock_price：获取股价→用于计算市盈率(PE)/市净率(PB)
#      📌 参数: symbol=股票代码(如002594)；period="realtime"/"daily"/"monthly"
#      🔥 历史年份分析：**必须传 target_date="{{年份}}-12-31"** 获取年末收盘价！
#    mcp_financial_statements：仅用于获取 SQL 不覆盖的科目（如少数股东权益等细节）
#    mcp_industry_comparison：行业横向对比
#    mcp_market_index：大盘指数数据
#    mcp_financial_calendar：财报日历/分红日程
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
9. 🔥 **多年份查询铁律**：用**一个** data_query 覆盖所有年份+所有指标（如"比亚迪 2023年 2024年 营业收入 净利润 总资产 净资产..."），不要拆成两个不同指标的查询！两个年份查到的指标集必须一致，否则增长率公式无法执行
10. 🔥 **依赖解耦铁律**：pe_ratio/pb_ratio 等需要股价的计算，**不应当**阻塞其他计算任务（毛利率/净利率/ROE等不需要股价）。做法：把不需要股价的 calculate 合并在一个任务里（formula 用逗号分隔），把 pe_ratio/pb_ratio 放在单独任务里只依赖股价查询，analyze 和 chart 不依赖股价任务

## ⚠️ 参数精确性铁律（违反则任务执行失败）
1. **formula 必须严格从上方"可用财务公式"列表中选取**，一字不差。需要多个公式时用逗号分隔："roe,net_profit_margin,gross_profit_margin"
2. **MCP 工具参数键名必须精确**。mcp_industry_comparison 的 sector 参数只能是 "白酒"/"新能源"/"互联网" 三个值
3. **chart_type 只能是** line/bar/pie/radar/dual_axis 五个值。多维度对比(≥3个不同量纲指标)用 radar，不要用 bar 硬塞
4. **depends_on 使用 task_id 字符串列表**，不要用数字
5. 🔥 **mcp_stock_price 的 symbol 参数必须是数字代码**（如 002594），不能传公司名

## ❌ 常见错误（千万不要犯）
- ❌ `"formula": "毛利率"` → 应该用 `"formula": "gross_profit_margin"`
- ❌ `"formula": "ROE"` → 应该用 `"formula": "roe"`
- ❌ `"params": {{"sector": "科技"}}` → sector 只能是 白酒/新能源/互联网
- ❌ `"params": {{"chart_type": "柱状图"}}` → 应该用 `"chart_type": "auto"`
- ❌ `"formula": ["roe", "net_profit_margin"]` → 应该用 `"formula": "roe,net_profit_margin"`
- ❌ `"params": {{"symbol": "比亚迪"}}` → 应该用 `"params": {{"symbol": "002594"}}`
- ❌ `"params": {{"symbol": "002594"}}` mcp_stock_price 无 target_date → 分析历史年份时必须加 `"params": {{"symbol": "002594", "target_date": "{{年份}}-12-31"}}`
- ❌ 两个 data_query 分别查 2023年2指标 和 2024年10指标 → 合并为**一个** query 覆盖两年全部指标
- ❌ 所有 calculate 都依赖 mcp_stock_price → pe_ratio/pb_ratio 单独放，其他计算不依赖股价
- ❌ analyze 依赖 mcp_stock_price → 股价只是估值指标之一，分析结论可以不含 PE/PB
"""

        # 🔧 复杂查询用 pro 保质量，简单查询用 flash 提速
        # 硬题 flash 频繁 JSON 空返回（浪费 20s+ 再切 pro），不值得
        # V8.4: LLM 拆解需要完整推理能力，始终用 pro
        task_type = TaskType.COMPLEX
        messages = [{"role": "user", "content": prompt}]

        plan_dict = self._try_llm_parse(messages, user_input, task_type)

        if plan_dict is None:
            logger.warning("LLM 拆解失败，回退为单任务直接分析")
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
