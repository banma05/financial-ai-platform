"""
Planner 单元测试 — 任务拆解逻辑 + 模板加载 + 追问检测
"""
import pytest
from unittest.mock import patch
from agent.planner import Planner, BUILTIN_TEMPLATES
from agent.schemas import AnalysisTask, AnalysisPlan


class TestPlannerTemplates:
    """模板加载测试"""

    def test_load_profitability_template(self):
        """加载盈利能力模板"""
        planner = Planner()
        plan = planner._load_template("profitability", "贵州茅台")
        assert len(plan.tasks) >= 5
        # 检查任务类型分布
        task_types = [t.task_type for t in plan.tasks]
        assert "data_query" in task_types
        assert "calculate" in task_types
        assert "chart" in task_types
        assert "analyze" in task_types

    def test_load_dupont_template(self):
        """加载杜邦分析模板"""
        planner = Planner()
        plan = planner._load_template("dupont", "比亚迪")
        assert len(plan.tasks) == 4
        # 验证依赖关系：calculate 依赖 data_query
        calc_task = next(t for t in plan.tasks if t.task_type == "calculate")
        assert len(calc_task.depends_on) > 0

    def test_load_growth_template(self):
        """加载成长性分析模板"""
        planner = Planner()
        plan = planner._load_template("growth", "腾讯")
        assert len(plan.tasks) == 6
        # 验证有双轴图表
        chart_task = next(t for t in plan.tasks if t.task_type == "chart")
        assert chart_task.params.get("chart_type") == "dual_axis"

    def test_template_company_injection(self):
        """验证 {company} 占位符在 params.query 中被正确替换"""
        planner = Planner()
        plan = planner._load_template("dupont", "贵州茅台2024年")
        data_query = next(t for t in plan.tasks if t.task_type == "data_query")
        # dupont 模板的 description 不含 {company}，params.query 含 {company}
        assert "贵州茅台2024年" in str(data_query.params["query"])

    def test_all_builtin_templates(self):
        """所有内置模板都应该可加载"""
        planner = Planner()
        for name in BUILTIN_TEMPLATES:
            plan = planner._load_template(name, "测试公司")
            assert len(plan.tasks) > 0, f"模板 {name} 加载失败"
            assert all(isinstance(t, AnalysisTask) for t in plan.tasks)

    def test_load_cash_flow_template(self):
        """加载现金流分析模板"""
        planner = Planner()
        plan = planner._load_template("cash_flow", "比亚迪")
        assert len(plan.tasks) == 6
        task_types = [t.task_type for t in plan.tasks]
        assert task_types.count("data_query") == 2
        assert task_types.count("calculate") == 2
        assert task_types.count("chart") == 1
        assert task_types.count("analyze") == 1
        # 验证公式使用
        formulas = [t.params.get("formula") for t in plan.tasks if t.params.get("formula")]
        assert "free_cash_flow" in formulas
        assert "cf_to_net_profit" in formulas

    def test_load_risk_scan_template(self):
        """加载财务风险扫描模板"""
        planner = Planner()
        plan = planner._load_template("risk_scan", "贵州茅台")
        assert len(plan.tasks) == 8
        task_types = [t.task_type for t in plan.tasks]
        assert task_types.count("data_query") == 2
        assert task_types.count("calculate") == 4
        assert task_types.count("chart") == 1
        assert task_types.count("analyze") == 1
        # 验证四个风险计算公式都存在
        formulas = [t.params.get("formula") for t in plan.tasks if t.params.get("formula")]
        assert "debt_ratio" in formulas
        assert "current_ratio" in formulas
        assert "quick_ratio" in formulas
        assert "interest_coverage" in formulas
        # 验证雷达图
        chart_task = next(t for t in plan.tasks if t.task_type == "chart")
        assert chart_task.params.get("chart_type") == "radar"

    def test_unknown_template(self):
        """未注册的模板名应该由 plan() 走 LLM 模式（此处只测不会崩溃）"""
        planner = Planner()
        # 必须 mock chat() 否则触发真实 LLM 调用
        with patch("agent.planner.chat", return_value='{"tasks": [], "requires_clarification": null}'):
            result = planner.plan("分析茅台", template_name=None)
        assert isinstance(result, AnalysisPlan)


class TestPlannerLLM:
    """LLM 拆解测试（mock chat()）"""

    NORMAL_JSON = """{
  "tasks": [
    {"task_id": "1", "task_type": "data_query", "description": "查询茅台营收", "params": {"query": "茅台营收"}, "depends_on": []},
    {"task_id": "2", "task_type": "calculate", "description": "计算毛利率", "params": {"formula": "gross_profit_margin"}, "depends_on": ["1"]},
    {"task_id": "3", "task_type": "chart", "description": "生成趋势图", "params": {"chart_type": "line"}, "depends_on": ["1"]},
    {"task_id": "4", "task_type": "analyze", "description": "分析结论", "params": {}, "depends_on": ["2", "3"]}
  ],
  "requires_clarification": null
}"""

    CLARIFY_JSON = """{
  "tasks": [],
  "requires_clarification": "请问您要分析哪家公司的数据？"
}"""

    WRAPPED_JSON = """```json
{
  "tasks": [
    {"task_id": "1", "task_type": "data_query", "description": "测试", "params": {}, "depends_on": []}
  ],
  "requires_clarification": null
}
```"""

    def test_parse_with_llm_success(self):
        """LLM 返回正常 JSON 应该正确解析"""
        with patch("agent.planner.chat", return_value=self.NORMAL_JSON):
            planner = Planner()
            plan = planner._parse_with_llm("分析贵州茅台")
        assert len(plan.tasks) == 4
        assert plan.requires_clarification is None
        calc_task = next(t for t in plan.tasks if t.task_type == "calculate")
        assert "1" in calc_task.depends_on

    def test_parse_with_llm_clarification(self):
        """LLM 返回追问内容"""
        with patch("agent.planner.chat", return_value=self.CLARIFY_JSON):
            planner = Planner()
            plan = planner._parse_with_llm("分析毛利率")
        assert plan.requires_clarification is not None
        assert "哪家公司" in plan.requires_clarification

    def test_parse_with_llm_json_error_fallback(self):
        """LLM 返回非法 JSON 应该触发回退"""
        with patch("agent.planner.chat", return_value="这不是合法的 JSON 格式"):
            planner = Planner()
            plan = planner._parse_with_llm("随便分析点东西")
        assert len(plan.tasks) >= 1
        assert plan.tasks[0].task_type == "data_query"

    def test_parse_with_llm_wrapped_json(self):
        """LLM 返回 ```json...``` 包裹的 JSON"""
        with patch("agent.planner.chat", return_value=self.WRAPPED_JSON):
            planner = Planner()
            plan = planner._parse_with_llm("测试")
        assert len(plan.tasks) == 1


class TestPlannerAmbiguity:
    """追问检测测试"""

    def test_detect_ambiguity_no_company(self):
        """没有指定公司 → 需要追问"""
        planner = Planner()
        result = planner._detect_ambiguity("毛利率是多少")
        assert result is not None
        assert "公司" in result

    def test_detect_ambiguity_no_indicator(self):
        """没有指定指标 → 需要追问"""
        planner = Planner()
        result = planner._detect_ambiguity("分析茅台2024年")
        assert result is not None

    def test_detect_ambiguity_clear(self):
        """需求明确 → 不需要追问"""
        planner = Planner()
        result = planner._detect_ambiguity("茅台2024年毛利率和净利率")
        assert result is None
