"""
DAG 拓扑排序工具 — Kahn 算法分层

消除 graph.py 和 executor.py 中的重复实现。
"""
from typing import List, Dict


def topological_layers(tasks: List[dict]) -> List[List[dict]]:
    """
    Kahn 算法分层拓扑排序。

    将任务按依赖关系分层，同层任务之间无依赖关系，可并行执行。

    参数:
        tasks: 任务 dict 列表，每个任务含 task_id 和 depends_on 字段

    返回:
        [[layer0_tasks], [layer1_tasks], ...]
        同层任务无相互依赖，层与层之间保证依赖顺序

    异常处理:
        存在循环依赖时，剩余任务全部放入最后一层
    """
    if not tasks:
        return []

    task_map = {t["task_id"]: t for t in tasks}
    in_degree: Dict[str, int] = {t["task_id"]: len(t.get("depends_on", [])) for t in tasks}
    adjacency: Dict[str, List[str]] = {t["task_id"]: [] for t in tasks}

    for t in tasks:
        for dep_id in t.get("depends_on", []):
            if dep_id in adjacency:
                adjacency[dep_id].append(t["task_id"])

    layers = []
    while in_degree:
        # 找到所有入度为 0 的节点（当前层）
        current = [tid for tid, deg in in_degree.items() if deg == 0]
        if not current:
            # 存在循环依赖，剩余任务全部放入最后一层
            remaining = [task_map[tid] for tid in in_degree]
            if remaining:
                layers.append(remaining)
            break

        layers.append([task_map[tid] for tid in current])

        # 移除当前层节点，更新入度
        for tid in current:
            del in_degree[tid]
            for neighbor in adjacency[tid]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1

    return layers
