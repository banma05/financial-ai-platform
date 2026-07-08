"""
对比 Agent（V6.0 新增）— 从多公司执行结果中抽取指标并生成对比报告

触发条件：plan 使用 cross_company_profit 模板，或 results 中包含多家公司的数据。
"""
from typing import List, Dict, Any
from loguru import logger


class Comparator:
    """
    对比智能体：提取多公司数据，生成结构化对比表格。

    不调用 LLM——纯数据整理。Reporter 后续可以用 LLM 润色对比分析。
    """

    def compare(self, tasks: List[dict], results: List[dict]) -> Dict[str, Any]:
        """
        从含多公司数据的执行结果中抽取核心指标，生成对比表。

        返回:
            {
                "companies": [...],         # 发现的公司列表
                "metrics": [...],           # 可对比的指标列表
                "comparison_table": [...],  # 结构化对比数据 [{metric, company_a, company_b, diff_pct}]
                "summary": str,             # 人类可读摘要
            }
        """
        # 从所有成功的结果中收集数据
        all_data = {}
        for r in results:
            if not r.get("success", False):
                continue
            data = r.get("data", {})
            if isinstance(data, dict):
                # 展平 nested data
                for k, v in data.items():
                    if isinstance(v, (int, float)) and not k.startswith("_"):
                        all_data[k] = v
                # 也看 data.data
                inner = data.get("data", {})
                if isinstance(inner, dict):
                    for k, v in inner.items():
                        if isinstance(v, (int, float)) and not k.startswith("_"):
                            all_data[k] = v
            # 计算结果的 result 值
            calc_result = data.get("result")
            if isinstance(calc_result, (int, float)):
                metric_name = data.get("display_name", "")
                if metric_name:
                    all_data[metric_name] = calc_result

        if len(all_data) < 2:
            return {"companies": [], "metrics": [], "comparison_table": [],
                    "summary": "数据不足以生成对比分析"}

        # 识别指标和公司
        metrics = []
        companies = set()
        for k in all_data:
            if "_" in k:
                # 格式: "营业收入_2024" 或 "净利润_比亚迪"
                parts = k.rsplit("_", 1)
                metrics.append(parts[0])
                companies.add(parts[1])
        companies = list(companies)
        metrics = list(set(metrics))

        # 如果从扁平数据中无法提取结构，回退到简单列表
        if not companies or not metrics:
            companies = ["数据"]
            metrics = list(all_data.keys())

        # 构建对比表
        comparison_table = []
        for metric in sorted(metrics):
            row = {"metric": metric}
            values = []
            for comp in companies:
                key = f"{metric}_{comp}" if len(companies) > 1 else metric
                val = all_data.get(key, all_data.get(metric, None))
                row[comp] = val
                if isinstance(val, (int, float)):
                    values.append(val)
            # 计算百分比差异（如果有两个值）
            if len(values) == 2 and all(v and v != 0 for v in values):
                diff_pct = round((values[0] - values[1]) / abs(values[1]) * 100, 1)
                row["diff_pct"] = diff_pct
            comparison_table.append(row)

        summary = f"对比 {len(companies)} 组数据，{len(metrics)} 个指标"
        if companies:
            summary += f"（{' vs '.join(companies)}）"

        logger.info(f"[Comparator] {summary}")
        return {
            "companies": companies,
            "metrics": metrics,
            "comparison_table": comparison_table,
            "summary": summary,
        }
