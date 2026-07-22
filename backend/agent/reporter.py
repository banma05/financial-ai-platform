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
        data_sources = {}  # V8.5: 追踪每个键的来源，用于冲突检测
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
                    source = r.data.get("source", "unknown")
                    source_conf = r.data.get("confidence", 0.5)
                    for k, v in r.data["data"].items():
                        if k in data_values:
                            existing_val = data_values[k]
                            if isinstance(v, (int, float)) and isinstance(existing_val, (int, float)):
                                # 检测冲突：相对差异 > 5% 视为冲突
                                rel_diff = abs(v - existing_val) / max(abs(existing_val), 0.01)
                                if rel_diff > 0.05:
                                    logger.warning(
                                        f"[数据冲突] '{k}': 旧值={existing_val}("
                                        f"来自{data_sources.get(k, '?')}), "
                                        f"新值={v}(来自{source}), 保留旧值"
                                    )
                                    continue  # 保留先到的值，不覆盖
                        data_values[k] = v
                        data_sources[k] = f"{source}(conf={source_conf})"
            elif r.task_type == "calculate" and r.data:
                calc_results.append(r.data)
            elif r.task_type == "rag_context":  # V8.0
                if isinstance(r.data, dict):
                    if r.data.get("insights"):
                        rag_insights.extend(r.data["insights"])
                    if r.data.get("quotations"):
                        rag_quotations.extend(r.data["quotations"])

        # ── V8.4: 6章专业研报结构 ──
        sections = []

        # 一、摘要（纯规则）
        sections.append(self._build_summary(user_input, tasks, results))

        # 二、数据概览（纯规则，增强版分组表格）
        if data_values:
            overview = self._build_data_overview_v2(data_values)
            if overview:
                sections.append(overview)

        # 三、分维度分析（含指标表格 + LLM 解读）
        if calc_results:
            sections.append(self._build_dimension_analysis(data_values, calc_results, user_input))

        # RAG 原文解读（如有）— 嵌入分维度分析而非单独成节
        if rag_insights or rag_quotations:
            sections.append(self._build_rag_section(rag_insights, rag_quotations))

        # 四、图表解读（纯规则）
        if chart_count > 0:
            sections.append(self._build_chart_interpretation(data_values, calc_results, chart_count))

        # 五、风险评估（纯规则，阈值判断）
        if self._has_risk_data(calc_results):
            sections.append(self._build_risk_assessment(calc_results))

        # 六、结论与建议（LLM，带数值校验 + RAG 解读引用）
        insights = self._generate_insights(user_input, data_values, calc_results, rag_insights)
        if insights:
            sections.append(insights)

        # 七、数据可靠度说明（V9.0: 让用户知道哪些数据可引用）
        sections.append(self._build_confidence_section(results, data_values))

        return "\n\n".join(sections)

    # ============ V8.4: 新增专业报告方法 ============

    @staticmethod
    def _has_risk_data(calc_results: List[dict]) -> bool:
        """检测是否有风险评估所需的数据"""
        risk_indicators = ["资产负债率", "流动比率", "速动比率", "利息保障倍数", "debt_ratio", "current_ratio"]
        for cr in calc_results:
            if cr.get("is_batch") and cr.get("results"):
                for item in cr["results"]:
                    name = item.get("display_name", "")
                    if any(ri in name for ri in risk_indicators):
                        return True
        return False

    def _build_data_overview_v2(self, data_values: dict) -> str:
        """V8.4: 增强版数据概览 — 按年份分组表格"""
        import re
        lines = ["## 二、数据概览", ""]

        # 按基础指标名分组，提取多年数据
        groups: dict = {}
        for k, v in data_values.items():
            base = re.sub(r'_\d{4}$', '', str(k))
            year_match = re.search(r'_(\d{4})$', str(k))
            year = year_match.group(1) if year_match else "-"
            if base not in groups:
                groups[base] = {}
            groups[base][year] = v

        if not groups:
            return ""

        # 收集所有年份
        all_years = sorted(set(y for g in groups.values() for y in g))

        # 表格头
        lines.append("| 指标 | " + " | ".join(all_years) + " |")
        lines.append("|------|" + "|".join(["------"] * len(all_years)) + "|")

        for base, year_vals in groups.items():
            vals = [self._fmt_num(year_vals.get(y, 0)) if year_vals.get(y) is not None else "-" for y in all_years]
            lines.append(f"| {base} | " + " | ".join(vals) + " |")

        return "\n".join(lines)

    def _build_dimension_analysis(self, data_values: dict,
                                   calc_results: List[dict], user_input: str) -> str:
        """V8.4: 分维度分析 — 指标表格 + LLM 解读"""
        # 指标表格（复用已有逻辑）
        indicator_section = self._build_indicator_analysis(calc_results)

        # LLM 维度解读
        context_parts = ["## 三、分维度分析", ""]
        context_parts.append(indicator_section.replace("## 三、指标计算", "### 指标明细"))
        context_parts.append("")

        # 简化 LLM 解读（只要求按维度解读事实，不要建议）
        if data_values or calc_results:
            prompt_parts = [f"基于以下财务数据，按维度（盈利能力/偿债能力/成长能力/营运效率）进行简要解读。"]
            prompt_parts.append("每个维度 1-2 句话，只描述事实和趋势，不做投资建议。")
            prompt_parts.append(f"\n{indicator_section}")
            try:
                from rag.model_router import chat, TaskType
                interpretation = chat(
                    [{"role": "user", "content": "\n".join(prompt_parts)}],
                    query=user_input, task_type=TaskType.SIMPLE,
                )
                context_parts.append(f"### 分维度解读\n\n{interpretation}")
            except Exception:
                pass

        return "\n".join(context_parts)

    def _build_chart_interpretation(self, data_values: dict,
                                     calc_results: List[dict], chart_count: int) -> str:
        """V8.4: 图表解读 — 纯规则，零 LLM"""
        lines = ["## 四、图表解读", ""]

        if not calc_results:
            lines.append(f"> 本次分析共生成 {chart_count} 张图表，请在下方查看。")
            return "\n".join(lines)

        for i, cr in enumerate(calc_results, 1):
            if cr.get("is_batch") and cr.get("results"):
                name = cr.get("display_name", f"维度{i}")
                items = [r for r in cr["results"] if r.get("success")]
                if items:
                    # 找最大值和最小值
                    values = [(r.get("display_name", ""), r.get("result", 0)) for r in items]
                    if len(values) >= 2:
                        best = max(values, key=lambda x: x[1])
                        worst = min(values, key=lambda x: x[1])
                        lines.append(f"- **{name}**：共 {len(items)} 项指标，" +
                                     f"最高为 {best[0]}({best[1]})，" +
                                     f"最低为 {worst[0]}({worst[1]})")

        lines.append(f"\n> 📊 共 {chart_count} 张图表，请在报告下方查看交互式可视化。")
        return "\n".join(lines)

    def _build_risk_assessment(self, calc_results: List[dict]) -> str:
        """V8.4: 风险评估 — 纯规则阈值判断，零 LLM"""
        lines = ["## 五、风险评估", ""]
        risks = []
        all_items = []

        # 收集所有指标值（V8.4: 杜邦分析已在 financial_calc 展开为标量，此处正常收集即可）
        for cr in calc_results:
            if cr.get("is_batch") and cr.get("results"):
                for item in cr["results"]:
                    result = item.get("result")
                    if result is not None and isinstance(result, (int, float)):
                        all_items.append(item)

        for item in all_items:
            name = item.get("display_name", "")
            val = item.get("result")
            if val is None:
                continue
            # 跳过非数值结果（如杜邦分析返回的 dict）
            if not isinstance(val, (int, float)):
                continue

            if "资产负债率" in name:
                if val > 70:
                    risks.append(f"🔴 **{name} {val}%** — 高杠杆 (>70%)，需关注偿债压力")
                elif val > 60:
                    risks.append(f"🟡 **{name} {val}%** — 中等杠杆 (60-70%)")
                else:
                    risks.append(f"🟢 **{name} {val}%** — 低杠杆 (<60%)，财务保守")

            elif "流动比率" in name:
                if val < 1.0:
                    risks.append(f"🔴 **{name} {val}倍** — 短期偿债压力大 (<1.0)")
                elif val < 2.0:
                    risks.append(f"🟡 **{name} {val}倍** — 正常范围 (1.0-2.0)")
                else:
                    risks.append(f"🟢 **{name} {val}倍** — 流动性充裕 (>2.0)")

            elif "速动比率" in name:
                if val < 0.5:
                    risks.append(f"🔴 **{name} {val}倍** — 严重流动性风险 (<0.5)")
                elif val < 1.0:
                    risks.append(f"🟡 **{name} {val}倍** — 流动性偏紧 (0.5-1.0)")

            elif "现金流" in name and "净利润" in name:
                if val < 50:
                    risks.append(f"🔴 **{name} {val}%** — 利润质量偏低 (<50%)")
                elif val < 100:
                    risks.append(f"🟡 **{name} {val}%** — 利润质量一般 (50-100%)")
                else:
                    risks.append(f"🟢 **{name} {val}%** — 利润质量优秀 (>100%)")

        if not risks:
            lines.append("> 基于当前数据，未发现明显财务风险。")
        else:
            for r in risks:
                lines.append(f"- {r}")

            # 判断综合风险等级
            red_count = sum(1 for r in risks if "🔴" in r)
            if red_count >= 2:
                lines.append(f"\n**综合风险等级：🔴 高风险** — 存在 {red_count} 项高危指标，建议重点关注。")
            elif red_count >= 1:
                lines.append(f"\n**综合风险等级：🟡 中等风险** — 存在 {red_count} 项需关注的指标。")
            else:
                lines.append(f"\n**综合风险等级：🟢 低风险** — 主要指标均在安全范围内。")

        return "\n".join(lines)

    def _build_summary(
        self, user_input: str, tasks: List[AnalysisTask], results: List[TaskResult]
    ) -> str:
        """V9.0: 构建执行摘要 — 核心发现而非任务清单"""
        # 提取计算指标
        key_metrics = []
        for r in results:
            if r.task_type == "calculate" and r.success and r.data:
                name = r.data.get("display_name", "")
                val = r.data.get("result")
                unit = r.data.get("unit", "")
                if name and val is not None:
                    key_metrics.append(f"{name}：{self._fmt_num(val)}{unit}")

        # 提取 RAG 洞察
        rag_found = False
        for r in results:
            if r.task_type == "rag_context" and r.success:
                rag_found = True
                break

        # 统计
        success_count = sum(1 for r in results if r.success)
        total = len(results)
        has_issues = success_count < total
        failed_tasks = [(t.description, r.error) for t, r in zip(tasks, results)
                       if not r.success and t.task_type != "analyze"]

        lines = ["## 一、执行摘要", ""]
        lines.append(f"**分析需求：**{user_input}")
        lines.append("")

        if key_metrics:
            lines.append("**核心指标：**")
            for m in key_metrics:
                lines.append(f"- {m}")
            lines.append("")

        if rag_found:
            lines.append("📄 已从年报原文中检索相关解读，详见分维度分析章节。")
            lines.append("")

        if has_issues:
            lines.append(f"**数据说明：**{success_count}/{total} 项分析完成")
            if failed_tasks:
                for desc, err in failed_tasks[:3]:
                    reason = (err or "数据缺失")[:40]
                    lines.append(f"- {desc}：{reason}")

        return "\n".join(lines)

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
            # ── V8.3: 批量计算结果展开为表格（即使部分失败也展示成功的）──
            if cr.get("is_batch") and cr.get("results"):
                display_name = cr.get("display_name", "指标")
                lines.append(f"\n### {display_name}")

                # 先展示成功的指标
                succeeded = [item for item in cr["results"] if item.get("success")]
                if succeeded:
                    lines.append("| 指标 | 计算结果 |")
                    lines.append("|------|----------|")
                    for item in succeeded:
                        name = item.get("display_name", "")
                        result = item.get("result", "")
                        unit = item.get("unit", "")
                        lines.append(f"| {name} | {result}{unit} |")
                    lines.append("")

                # 再展示失败的公式
                failed = [item for item in cr["results"] if not item.get("success")]
                if failed:
                    failed_names = [f.get("display_name") or f.get("formula", "?") for f in failed]
                    lines.append(f"\n❌ 以下公式计算失败：{', '.join(failed_names)}")
                    for item in failed:
                        lines.append(f"  - **{item.get('display_name', item.get('formula', '?'))}**：{item.get('error', '计算失败')}")
                lines.append("")
            elif not cr.get("success"):
                lines.append(f"\n- ❌ **{cr.get('display_name', '未知指标')}**：{cr.get('error', '计算失败')}")
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

    def _build_confidence_section(self, results: List, data_values: dict) -> str:
        """V9.0: 构建数据可靠度说明 — 让用户知道哪些数字可引用、哪些是推算的"""
        lines = ["## 七、数据可靠度说明", ""]

        # 分析每个 TaskResult 的 source
        has_fallback = False
        has_computed = False
        has_rag = False
        total_confidence = 0.0
        confidence_count = 0

        for r in results:
            if not isinstance(r, dict):
                continue
            source = r.get("source", "")
            conf = r.get("confidence")

            if isinstance(conf, (int, float)):
                total_confidence += conf
                confidence_count += 1

            if "fallback" in str(source):
                has_fallback = True
            if "computed" in str(source) or "auto_fill" in str(source):
                has_computed = True
            if "rag" in str(source).lower():
                has_rag = True

        # 整体置信度
        if confidence_count > 0:
            avg_conf = total_confidence / confidence_count
            if avg_conf >= 0.90:
                conf_label = "高"
            elif avg_conf >= 0.75:
                conf_label = "中"
            else:
                conf_label = "低"
            lines.append(f"**整体数据可靠度：{conf_label}**（置信度 {avg_conf:.0%}）")
            lines.append("")

        # 分类说明
        lines.append("| 数据来源 | 说明 |")
        lines.append("|:---|:---|")
        lines.append("| SQL 直查 | 直接从财务数据库获取，准确度最高 |")
        if has_fallback:
            lines.append("| 字段回退 | 目标字段缺失，使用替代字段（如归母净利润←净利润），准确度较高 |")
        if has_computed:
            lines.append("| 公式推算 | 部分参数通过已有数据计算得出（如每股净资产由EPS反推），准确度中等 |")
        if has_rag:
            lines.append("| 年报解读 | 从年报原文检索提炼的定性分析，仅供参考 |")
        lines.append("")
        lines.append("> 提示：报告中标注 *(推算)* 的数值为间接计算得出，建议在引用前与原始年报核对。")
        lines.append("> 所有数据基于已披露年报，不构成投资建议。")

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

        # V8.5: 同时支持单公式和批量计算结果
        for cr in calc_results:
            if cr.get("is_batch") and cr.get("results"):
                for item in cr["results"]:
                    if item.get("success") and item.get("result") is not None:
                        if isinstance(item["result"], (int, float)):
                            r = item["result"]
                            allowed_values.add(str(r))
                            allowed_values.add(self._fmt_num(r))
            elif cr.get("success") and cr.get("result") is not None:
                if isinstance(cr["result"], (int, float)):
                    r = cr["result"]
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
            warning_note = (
                "\n\n> ⚠️ **数据一致性提示**：AI 生成的分析结论中检测到部分数字与原始数据源"
                "存在差异，以上分析仅供参考。请以「二、数据概览」和「三、分维度分析」表格中的"
                "精确值为准。"
            )
            return response + warning_note

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
