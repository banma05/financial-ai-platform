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
        rag_insights = []  # V8.0: RAG 文字解读
        rag_quotations = []  # V8.0: 原文引用

        for r in results:
            if not r.success:
                continue
            if r.task_type == "data_query":
                if r.summary:
                    data_summaries.append(r.summary)
                if isinstance(r.data, dict) and r.data.get("data"):
                    data_values.update(r.data["data"])
            elif r.task_type == "calculate" and r.data:
                calc_results.append(r.data)
            elif r.task_type == "rag_context":  # V8.0
                if isinstance(r.data, dict):
                    if r.data.get("insights"):
                        rag_insights.extend(r.data["insights"])
                    if r.data.get("quotations"):
                        rag_quotations.extend(r.data["quotations"])

        # 构建报告各章节
        sections = []

        # 一、分析摘要
        sections.append(self._build_summary(user_input, tasks, results))

        # 二、数据概览
        if data_summaries and data_values:
            overview = self._build_data_overview(data_summaries, data_values)
            if overview:
                sections.append(overview)

        # 三、指标分析
        if calc_results:
            sections.append(self._build_indicator_analysis(calc_results))

        # 三、RAG 原文解读（V8.0 新增）
        if rag_insights or rag_quotations:
            sections.append(self._build_rag_section(rag_insights, rag_quotations))

        # 四、图表展示（占位符，前端替换为实际图片）
        if chart_count > 0:
            sections.append(self._build_chart_section(chart_count))

        # 五、结论与建议（LLM 生成，含 RAG 上下文）
        # V8.2: 传入 data_values（结构化精确值）替代 data_summaries（文本），根除 LLM 数字幻觉
        insights = self._generate_insights(user_input, data_values, calc_results, rag_insights)
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

    def _build_data_overview(self, summaries: List[str], data_values: dict) -> str:
        """构建数据概览 — 数据已从 SQL 查得，直接格式化展示"""
        if not data_values:
            return ''
        items = []
        for k, v in data_values.items():
            items.append(f'- {k}: {self._fmt_num(v)}')
        return f"""## 二、数据概览

{chr(10).join(items)}"""

    @staticmethod
    def _fmt_num(v: float) -> str:
        if abs(v) >= 1e8: return f'{v/1e8:.2f}亿'
        if abs(v) >= 1e4: return f'{v/1e4:.2f}万'
        if isinstance(v, float) and v == int(v): return f'{int(v)}'
        return f'{v:.2f}'

    def _build_indicator_analysis(self, calc_results: List[dict]) -> str:
        """构建指标分析章节（支持批量计算 + 单公式计算）"""
        lines = ["## 三、指标计算"]

        for cr in calc_results:
            if not cr.get("success"):
                lines.append(f"\n- ❌ **{cr.get('display_name', '未知指标')}**：{cr.get('error', '计算失败')}")
                continue

            # ── V8.3: 批量计算结果展开为表格 ──
            if cr.get("is_batch") and cr.get("results"):
                # 按类别分组
                display_name = cr.get("display_name", "指标")
                lines.append(f"\n### {display_name}")
                lines.append("| 指标 | 计算结果 |")
                lines.append("|------|----------|")
                for item in cr["results"]:
                    if item.get("success"):
                        name = item.get("display_name", "")
                        result = item.get("result", "")
                        unit = item.get("unit", "")
                        lines.append(f"| {name} | {result}{unit} |")
                lines.append("")
            else:
                # 单公式计算结果
                display = cr.get('display_name', '指标')
                result = cr.get('result')
                unit = cr.get('unit', '')
                if result is not None:
                    lines.append(f"\n- **{display}**：{result}{unit}")
                else:
                    expression = cr.get('expression', '')
                    lines.append(f"\n- **{display}**：{expression}")

        return "\n".join(lines)

    def _build_rag_section(self, insights: List[str], quotations: List[dict]) -> str:
        """构建 RAG 原文解读章节"""
        lines = ["## 四、原文解读（来自年报/研报）\n"]
        if insights:
            for ins in insights:
                lines.append(f"- {ins}")
        if quotations:
            lines.append("\n**原文引用：**")
            for q in quotations[:3]:
                src = f"{q.get('source','')} 第{q.get('page','')}页"
                lines.append(f"\n> {q['text'][:200]}...\n> — *{src}*")
        return "\n".join(lines)

    def _build_chart_section(self, chart_count: int) -> str:
        """构建图表展示章节"""
        return f"""## 五、可视化图表

> 共生成 {chart_count} 张图表，请在报告下方查看。"""

    def _generate_insights(
        self, user_input: str, data_values: dict,
        calc_results: List[dict], rag_insights: List[str] = None,
    ) -> str:
        """
        LLM 生成分析洞察和建议（V8.2 深层修复：用结构化数据替代文本，消除数字幻觉）。

        V8.2 根因修复：
        - 旧版传入 data_summaries（文本），LLM 需要"阅读"文本再提取数字 → 引入幻觉
        - 新版传入 data_values（dict），以表格呈现精确值，LLM 只需引用 → 零幻觉
        - 添加铁律约束：禁止修改任何数字，禁止四舍五入，禁止凭记忆补充
        """
        if not data_values and not calc_results:
            return ""

        # ── 构建结构化数据表格（V8.2：替代旧版文本拼接）──
        context_parts = [f"## 用户需求\n{user_input}\n"]

        # 数据概览表格
        if data_values:
            context_parts.append("## 精确数据表（⚠️ 以下数值为权威来源，必须严格使用，禁止修改）\n")
            context_parts.append("| 指标名称 | 精确数值 |")
            context_parts.append("|----------|----------|")
            for k, v in data_values.items():
                context_parts.append(f"| {k} | {self._fmt_num(v)} |")
            context_parts.append("")

        # 计算结果（含批量展开）
        if calc_results:
            context_parts.append("## 指标计算结果（⚠️ 以下数值已经过精确计算，禁止重新计算或估算）\n")
            context_parts.append("| 指标 | 计算结果 | 计算公式 |")
            context_parts.append("|------|----------|----------|")
            for cr in calc_results:
                # ── V8.3: 展开批量计算结果 ──
                if cr.get("is_batch") and cr.get("results"):
                    for item in cr["results"]:
                        if item.get("success") and item.get("result") is not None:
                            display = item.get("display_name", "指标")
                            result = item.get("result", "")
                            expr = item.get("expression", "")
                            unit = item.get("unit", "")
                            context_parts.append(f"| {display} | {result}{unit} | {expr} |")
                elif cr.get("success") and cr.get("result") is not None:
                    display = cr.get("display_name", "指标")
                    result = cr.get("result", "")
                    expr = cr.get("expression", "")
                    context_parts.append(f"| {display} | {result}{cr.get('unit', '')} | {expr} |")
            context_parts.append("")

        # RAG 原文解读
        if rag_insights:
            context_parts.append("## 年报/研报原文解读（仅供参考，不覆盖数据表中的精确值）\n")
            for ins in rag_insights:
                context_parts.append(f"- {ins}")
            context_parts.append("")

        context = "\n".join(context_parts)

        prompt = f"""{context}

请基于以上精确数据，生成专业的财务分析结论。

## ⚠️ 数字准确性铁律（违反任一条即为严重错误）

1. **只能使用上面表格中的精确数值**，不得做任何修改
2. **禁止四舍五入**：表中写 36.99 就必须写 36.99，不能写"约37"或"37%"
3. **禁止自行计算**：所有指标值已在上面给出，不要重新计算（可能因精度差异产生偏差）
4. **禁止凭记忆补充**：即使你知道某公司的其他数据，如果上面表格中没有，就不能写
5. **数据不足就说不足**：如果某个分析维度缺少数据，坦诚说明，不要编造

## 输出格式要求

1. **核心发现**（2-3 条）：从数据中提炼最关键的趋势或异常，每个数字必须与上面表格一致
2. **分析解读**：解释指标背后的业务含义
3. **建议**（1-2 条）：基于分析给出合理建议
4. 语言简洁专业，每条控制在 2-3 句话
5. 每条核心发现和建议后标注置信度 `[置信度: XX%]`
   - 数据充分且结论明确：85-95%
   - 部分推断或数据有限：60-80%
   - 高度不确定：30-55%

输出格式（Markdown）：
## 六、结论与建议

### 核心发现
- **发现1**：...[置信度: 85%]
- **发现2**：...[置信度: 70%]

### 分析解读
...

### 建议
- **建议1**：...[置信度: 80%]"""

        try:
            messages = [
                {"role": "system", "content": (
                    "你是一位资深财务分析师。你的分析必须严格基于提供的精确数据表。"
                    "表中的每个数字都是权威来源，禁止修改、禁止四舍五入、禁止自行计算、禁止凭记忆补充。"
                    "如果表格中没有某个数据，就坦诚说缺少该数据。"
                )},
                {"role": "user", "content": prompt},
            ]
            response = chat(messages, query=user_input, task_type=TaskType.SIMPLE)
            # ── V8.2: 后处理数值校验 ──
            return self._verify_numbers(response, data_values, calc_results)
        except Exception as e:
            logger.warning(f"LLM 生成洞察失败: {e}")
            # 降级：直接基于计算结果显示
            return self._build_fallback_insights(data_values, calc_results)

    def _verify_numbers(
        self, response: str, data_values: dict, calc_results: List[dict]
    ) -> str:
        """
        V8.2 后处理数值校验：检查 LLM 输出中的数字是否与数据源一致。

        策略：
        1. 先剔除元数据文本（置信度标注、Markdown 表格分隔行）避免误报
        2. 提取剩余文本中的数字，与 data_values 和 calc_results 对比
        3. 使用 1% 相对容差 + 0.1 绝对容差（兼容格式化后的数值差异）
        4. 发现不一致时记录警告（不修改输出，保持可读性，但标记潜在幻觉供评测追踪）
        """
        import re

        # ── 预处理：剔除元数据文本，避免误报 ──
        cleaned = response
        # 移除置信度标注 [置信度: XX%] 及其中的数字
        cleaned = re.sub(r'\[置信度[：:]\s*\d+%\]', '', cleaned)
        # 移除 Markdown 表格分隔行（如 |---|:--:|...）
        cleaned = re.sub(r'^\s*\|[\s\-:|]+\|\s*$', '', cleaned, flags=re.MULTILINE)

        # 提取清理后文本中的所有数字（含小数点）
        numbers_in_output = re.findall(r'\d+\.?\d*', cleaned)
        if not numbers_in_output:
            return response

        # 构建"允许出现的数字"集合（来自数据源）
        allowed_values = set()
        for v in data_values.values():
            if isinstance(v, (int, float)):
                allowed_values.add(str(v))
                allowed_values.add(self._fmt_num(v))

        for cr in calc_results:
            if cr.get("success") and cr.get("result") is not None:
                r = cr.get("result")
                allowed_values.add(str(r))
                allowed_values.add(self._fmt_num(r))

        # 解析所有允许值及其格式化变体为 float 列表（用于容差比较）
        allowed_floats = []
        for av in allowed_values:
            try:
                allowed_floats.append(float(av))
            except ValueError:
                pass

        # 检查输出中的数字
        suspicious = []
        for num in numbers_in_output:
            # 年份数字跳过
            if re.match(r'^20\d{2}$', num):
                continue
            # 小于 100 的整数跳过（通常是百分比置信度、序号等元数据，非财务数值）
            try:
                if '.' not in num and int(num) < 100:
                    continue
            except ValueError:
                continue

            # 精确匹配
            if num in allowed_values:
                continue

            # 容差匹配：1% 相对容差 或 0.1 绝对容差
            found_close = False
            try:
                num_f = float(num)
                for af in allowed_floats:
                    if af == 0:
                        continue
                    rel_diff = abs(num_f - af) / abs(af)
                    abs_diff = abs(num_f - af)
                    if rel_diff < 0.01 or abs_diff < 0.1:
                        found_close = True
                        break
            except ValueError:
                pass

            if not found_close:
                suspicious.append(num)

        if suspicious:
            logger.warning(
                f"[数值校验] 发现 {len(suspicious)} 个未在数据源中的数字: {suspicious[:5]}"
            )

        return response

    def _build_fallback_insights(self, data_values: dict, calc_results: List[dict]) -> str:
        """V8.2 降级方案：LLM 调用失败时，基于结构化数据直接生成结论（零 LLM）"""
        lines = ["## 六、结论与建议", "", "> ⚠️ AI 深度分析暂时不可用，以下为基于数据的自动摘要。"]
        lines.append("")
        lines.append("### 关键指标")
        for k, v in data_values.items():
            lines.append(f"- **{k}**：{self._fmt_num(v)}")
        for cr in calc_results:
            if cr.get("success") and cr.get("result") is not None:
                lines.append(f"- **{cr.get('display_name', '指标')}**：{cr['result']}{cr.get('unit', '')}")
        lines.append("")
        lines.append("*注：以上为自动生成的数据摘要。AI 深度分析生成失败，请手动解读或重试。*")
        return "\n".join(lines)
