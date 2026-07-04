"""
Reporter（报告生成器）— 将执行结果组装为结构化分析报告

报告结构：
## 一、分析摘要
## 二、数据概览
## 三、指标分析（含图表）
## 四、结论与建议
"""
from typing import List
from loguru import logger

from rag.model_router import chat, TaskType
from .schemas import AnalysisTask, TaskResult


class Reporter:
    """
    报告生成器：将各工具的执行结果汇总为 Markdown 分析报告。

    职责：
    1. 收集所有 task_results 中的数据和摘要
    2. 按章节组织报告结构
    3. LLM 生成分析结论和建议
    4. 图表引用嵌入报告
    """

    def __init__(self):
        pass  # LLM 调用统一走 chat()，无需持有实例

    def generate(
        self,
        user_input: str,
        tasks: List[AnalysisTask],
        results: List[TaskResult],
        chart_count: int = 0,
    ) -> str:
        """
        生成完整分析报告（Markdown 格式）。

        参数:
            user_input: 用户原始分析需求
            tasks: 任务列表
            results: 任务执行结果列表
            chart_count: 生成的图表数量

        返回:
            Markdown 格式的完整报告
        """
        # 收集数据
        data_summaries = []
        data_values = {}
        calc_results = []

        for r in results:
            if not r.success:
                continue
            if r.task_type == "data_query" and r.summary:
                data_summaries.append(r.summary)
                if isinstance(r.data, dict) and r.data.get("data"):
                    data_values.update(r.data["data"])
            elif r.task_type == "calculate" and r.data:
                calc_results.append(r.data)

        # 构建报告各章节
        sections = []

        # 一、分析摘要
        sections.append(self._build_summary(user_input, tasks, results))

        # 二、数据概览
        if data_summaries:
            sections.append(self._build_data_overview(data_summaries))

        # 三、指标分析
        if calc_results:
            sections.append(self._build_indicator_analysis(calc_results))

        # 四、图表展示（占位符，前端替换为实际图片）
        if chart_count > 0:
            sections.append(self._build_chart_section(chart_count))

        # 五、结论与建议（LLM 生成）
        insights = self._generate_insights(user_input, data_summaries, calc_results)
        if insights:
            sections.append(insights)

        return "\n\n".join(sections)

    def _build_summary(
        self, user_input: str, tasks: List[AnalysisTask], results: List[TaskResult]
    ) -> str:
        """构建分析摘要章节"""
        success_count = sum(1 for r in results if r.success)
        total_count = len(results)

        task_list = "\n".join(
            f"- {'✅' if r.success else '❌'} {task.description}" +
            (f" — {r.summary}" if r.summary else f" — *{r.error or '跳过'}*")
            for task, r in zip(tasks, results)
        )

        return f"""## 一、分析摘要

**分析需求：** {user_input}

**执行情况：** {success_count}/{total_count} 个子任务成功完成

**子任务详情：**
{task_list}"""

    def _build_data_overview(self, summaries: List[str]) -> str:
        """构建数据概览章节"""
        items = "\n".join(f"- {s}" for s in summaries)
        return f"""## 二、数据概览

{items}"""

    def _build_indicator_analysis(self, calc_results: List[dict]) -> str:
        """构建指标分析章节"""
        lines = ["## 三、指标计算"]

        for cr in calc_results:
            if cr.get("success"):
                lines.append(f"\n### {cr.get('display_name', '指标')}")
                lines.append(f"\n{cr.get('expression', '')}")
            else:
                lines.append(f"\n- ❌ {cr.get('display_name', '未知指标')}: {cr.get('error', '计算失败')}")

        return "\n".join(lines)

    def _build_chart_section(self, chart_count: int) -> str:
        """构建图表展示章节"""
        return f"""## 四、可视化图表

> 共生成 {chart_count} 张图表，请在报告下方查看。"""

    def _generate_insights(
        self, user_input: str, data_summaries: List[str], calc_results: List[dict]
    ) -> str:
        """LLM 生成分析洞察和建议"""
        if not data_summaries and not calc_results:
            return ""

        # 构建 LLM 上下文
        context = f"用户需求：{user_input}\n\n"

        if data_summaries:
            context += "## 检索到的数据\n" + "\n".join(f"- {s}" for s in data_summaries) + "\n\n"

        if calc_results:
            context += "## 计算结果\n"
            for cr in calc_results:
                if cr.get("success"):
                    context += f"- {cr.get('expression', '')}\n"

        prompt = f"""{context}

请基于以上数据和计算结果，生成一份专业的财务分析结论。要求：

1. **核心发现**（2-3 条）：从数据中提炼最关键的趋势或异常
2. **分析解读**：解释指标背后的业务含义
3. **建议**（1-2 条）：基于分析给出合理建议
4. 语言简洁专业，每条控制在 2-3 句话
5. 如果数据不足无法判断，坦诚说明而非编造

输出格式（Markdown）：
## 五、结论与建议

### 核心发现
...

### 分析解读
...

### 建议
..."""

        try:
            messages = [
                {"role": "system", "content": "你是一位资深的财务分析师。请基于提供的数据给出专业、诚实的分析。"},
                {"role": "user", "content": prompt},
            ]
            response = chat(messages, query=user_input, task_type=TaskType.SIMPLE)
            return response
        except Exception as e:
            logger.warning(f"LLM 生成洞察失败: {e}")
            return f"""## 五、结论与建议

> 基于以上数据指标，各项财务指标已计算完成。详细分析解读请参考指标计算章节。

*注：AI 深度分析生成失败（{e}），请手动解读。*"""
