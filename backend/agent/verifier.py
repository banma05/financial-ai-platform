"""
校验 Agent（V6.0 新增）— 独立审查执行结果的正确性和一致性

设计原则：
1. 纯规则检查（零 LLM 开销），在 reporter 之前运行
2. 发现问题时标记为 issues，reporter 可以选择展示或忽略
3. 不影响主流程：校验失败不阻塞报告生成
"""
from typing import List, Dict, Any
from loguru import logger


class Verifier:
    """
    校验智能体：检查 Executor 输出质量。

    检查维度：
    1. 完整性：所有任务都有结果
    2. 成功率：是否有失败任务
    3. 数据一致性：数值范围合理性
    """

    def verify(self, user_input: str, tasks: List[dict],
               results: List[dict]) -> Dict[str, Any]:
        """
        对完整执行结果进行校验。

        返回:
            {"passed": bool, "issues": [...], "warnings": [...],
             "success_rate": float, "total_tasks": int}
        """
        issues = []
        warnings = []
        total = len(results)
        success_count = sum(1 for r in results if r.get("success", False))
        success_rate = success_count / total if total > 0 else 0

        # 检查1: 空结果
        if total == 0:
            issues.append("没有任何任务执行结果")
            return {"passed": False, "issues": issues, "warnings": warnings,
                    "success_rate": 0.0, "total_tasks": 0}

        # 检查2: 任务有未完成
        pending = [t for t in tasks if t.get("task_id") not in
                   {r.get("task_id") for r in results}]
        if pending:
            warnings.append(f"{len(pending)} 个任务未返回结果: "
                           f"{[t['task_id'] for t in pending]}")

        # 检查3: 失败任务
        failed = [r for r in results if not r.get("success", False)]
        if failed:
            issues.append(f"{len(failed)}/{total} 个任务执行失败: "
                         f"{[r.get('task_id') for r in failed]}")

        # 检查4: 数据查询结果为空
        empty_queries = [
            r for r in results
            if r.get("task_type") == "data_query" and not r.get("data", {}).get("found", True)
        ]
        if empty_queries:
            warnings.append(f"{len(empty_queries)} 个数据查询未找到结果")

        # 检查5: 图表数量过多（可能影响报告可读性）
        chart_count = sum(1 for r in results if r.get("chart_base64"))
        if chart_count > 5:
            warnings.append(f"图表数量较多({chart_count})，报告可能较长")

        passed = len(issues) == 0 and success_rate >= 0.5
        logger.info(f"[Verifier] {'通过' if passed else '未通过'}: "
                    f"成功率 {success_rate:.0%}, {len(issues)} 问题, {len(warnings)} 警告")

        return {
            "passed": passed,
            "issues": issues,
            "warnings": warnings,
            "success_rate": round(success_rate, 2),
            "total_tasks": total,
            "failed_tasks": len(failed),
        }
