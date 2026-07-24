"""
V9.0 Agent 评测脚本 — 打破循环论证，多维度评分，按公司分离

核心改进（vs V8 bench_agent.py）：
1. 锚点验证 — 独立验证数字作为"地面真相"（打破循环论证）
2. 分层评分 — 模板题重数值准确性，自由拆解题重结构覆盖
3. 数据溯源率 — 报告中可追溯到 SQL 的数据点占比
4. 图表渲染率 — 期望图表中实际生成的比例
5. 行业基准引用 — 是否在适当时引用了行业对比
6. 按公司分离 — RAG vs 非RAG 分报告（避免知识库覆盖不足干扰）
7. 趋势追踪 — 每次评测持久化，可对比历史趋势

用法:
    cd D:\实战项目\financial-ai-platform
    source ../.venv/Scripts/activate
    python evaluation/agent/bench_agent_v9.py                    # 全量 V9 50题
    python evaluation/agent/bench_agent_v9.py --dataset v8       # 旧版 15题（兼容）
    python evaluation/agent/bench_agent_v9.py --quick            # 快速抽检 5题
"""
import os
import sys
import re
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Union
from collections import defaultdict

# ── Windows GBK 终端适配 ──
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# ── 轻量模式 ──
LIGHT_MODE = os.environ.get("EVAL_LIGHT", "1").lower() in ("1", "true", "yes")
if LIGHT_MODE:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["EVAL_LIGHT"] = "1"

import sentence_transformers  # noqa: 必须在其他 import 之前

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from loguru import logger
from agent.planner import Planner
from agent.schemas import AnalysisPlan
from agent.graph import run_agent_sync
from rag.model_router import init_usage, get_usage

# ════════════════════════════════════════════════════════════════
# 配置
# ════════════════════════════════════════════════════════════════

# 评分权重（模板题）
TEMPLATE_WEIGHTS = {
    "anchor_accuracy": 0.30,       # 锚点验证（最核心）
    "number_accuracy": 0.20,       # 数值准确性
    "traceability_rate": 0.15,     # 数据溯源率
    "chart_render_rate": 0.10,     # 图表渲染率
    "hallucination_score": 0.10,   # 幻觉检测
    "structural_coverage": 0.10,   # 结构覆盖
    "industry_benchmark": 0.05,    # 行业基准
}

# 评分权重（自由拆解题 — 不依赖精确数值，重推理能力）
FREEFORM_WEIGHTS = {
    "structural_coverage": 0.35,   # 结构覆盖（最重要）
    "hallucination_score": 0.20,   # 幻觉检测
    "traceability_rate": 0.15,     # 数据溯源率
    "number_accuracy": 0.10,       # 数值准确性（降权）
    "chart_render_rate": 0.10,     # 图表渲染率
    "industry_benchmark": 0.05,    # 行业基准
    "anchor_accuracy": 0.05,       # 锚点验证（降权）
}

# 生产级目标阈值
PRODUCTION_TARGETS = {
    "anchor_accuracy": 0.95,
    "number_accuracy": 0.85,
    "traceability_rate": 0.80,
    "chart_render_rate": 0.90,
    "structural_coverage": 0.80,
    "hallucination_score": 0.90,
    "industry_benchmark": 0.50,
    "avg_latency_template_s": 5.0,
    "avg_latency_freeform_s": 20.0,
    "overall_score": 0.85,
}


# ════════════════════════════════════════════════════════════════
# 数据加载 & 格式兼容
# ════════════════════════════════════════════════════════════════

def load_questions(dataset: str = "v9") -> Tuple[List[dict], dict]:
    """加载评测题集，兼容新旧格式。"""
    data_dir = Path(__file__).parent.parent / "data"

    if dataset == "v9":
        path = data_dir / "agent_questions_v9.json"
    else:
        path = data_dir / "agent_questions.json"

    if not path.exists():
        logger.error(f"评测集不存在: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data["questions"]
    # 过滤掉分隔注释（纯字符串元素）
    questions = [q for q in questions if isinstance(q, dict)]

    meta = data.get("meta", {})
    logger.info(f"加载评测集: {meta.get('name', 'unknown')} — {len(questions)} 题")
    return questions, meta


def normalize_required_numbers(question: dict) -> Dict[str, dict]:
    """
    兼容新旧 required_numbers 格式。

    旧格式: {"毛利率": 91.18, "净利率": 48.76}
    新格式: {"毛利率": {"value": 91.18, "tolerance_pct": 2, "source": "independently_verified"}}

    返回统一的新格式。
    """
    raw = question.get("required_numbers", {})
    if not raw:
        return {}

    normalized = {}
    for key, val in raw.items():
        if isinstance(val, (int, float)):
            # 旧格式 → 转换为新格式
            normalized[key] = {
                "value": float(val),
                "tolerance_pct": 3,  # 默认 3% 容差
                "source": "db_extracted",  # 旧数据标记为未验证
            }
        elif isinstance(val, dict):
            normalized[key] = {
                "value": float(val.get("value", 0)),
                "tolerance_pct": float(val.get("tolerance_pct", 3)),
                "source": val.get("source", "db_extracted"),
                "note": val.get("note", ""),
            }
    return normalized


# ════════════════════════════════════════════════════════════════
# 评分函数
# ════════════════════════════════════════════════════════════════

def _extract_indicator_name(key: str) -> str:
    """从键名中提取指标中文名（去公司/年份后缀）。

    "毛利率_贵州茅台" → "毛利率"
    "营业收入_2024" → "营业收入"
    "ROE_比亚迪" → "ROE"
    """
    # 去掉常见后缀
    suffixes = ["_贵州茅台", "_比亚迪", "_宁德时代", "_五粮液", "_招商银行",
                "_美的集团", "_格力电器", "_恒瑞医药", "_泸州老窖", "_洋河股份",
                "_中国平安", "_海康威视", "_伊利股份", "_长江电力", "_山西汾酒",
                "_隆基绿能", "_京东方A", "_科大讯飞", "_中芯国际", "_中信证券",
                "_平安银行",
                "_2020", "_2021", "_2022", "_2023", "_2024", "_2025", "_2026"]
    result = key
    for s in suffixes:
        if result.endswith(s):
            result = result[:-len(s)]
            break
    return result


def _check_indicator_number_association(report: str, indicator: str,
                                         expected: float,
                                         tolerance: float) -> Tuple[bool, str]:
    """
    核心: 检查指标名与数值在报告中的关联性。

    不只是检查数字是否存在，而是验证数字出现在指标名附近。
    搜索窗口: 指标名前后各 150 字符。
    """
    # 1. 找到报告中所有指标名出现的位置
    indicator_positions = []
    report_lower = report.lower()
    indicator_lower = indicator.lower()

    # 生成指标名的变体（中文/英文/缩写）
    variants = {indicator, indicator_lower}
    # 如果是复合键（如"毛利率_2024"），也搜索子部分
    if "_" in indicator:
        for part in indicator.split("_"):
            variants.add(part)
            variants.add(part.lower())

    for variant in variants:
        pos = 0
        while True:
            pos = report.find(variant, pos)
            if pos == -1:
                break
            indicator_positions.append(pos)
            pos += 1

    if not indicator_positions:
        return False, f"指标 '{indicator}' 在报告中未找到"

    # 2. 在每个指标名附近搜索期望数值
    window = 150  # 前后各150字符
    report_numbers = list(re.finditer(r'-?\d+\.?\d*', report))

    for ipos in indicator_positions:
        window_start = max(0, ipos - window)
        window_end = min(len(report), ipos + window)

        for num_match in report_numbers:
            num_pos = num_match.start()
            if window_start <= num_pos <= window_end:
                try:
                    num_val = float(num_match.group())
                except ValueError:
                    continue

                # 验证数值（含单位换算）
                candidates = {expected}
                for divisor in [1e4, 1e8]:
                    candidates.add(round(expected / divisor, 2))
                    candidates.add(round(expected / divisor, 1))
                    candidates.add(round(expected / divisor, 0))

                # 负值容忍
                if expected < 0:
                    abs_candidates = set()
                    for c in candidates:
                        abs_candidates.add(abs(c))
                    candidates.update(abs_candidates)

                for c in candidates:
                    if abs(c) < 0.01:
                        if abs(num_val) < 0.01:
                            return True, f"指标 '{indicator}' 关联到 {num_val} ≈ {expected}"
                    else:
                        rel_diff = abs(num_val - c) / abs(c)
                        if rel_diff < tolerance:
                            return True, f"指标 '{indicator}' 关联到 {num_val} ≈ {expected} (容差{rel_diff:.1%})"

    return False, f"指标 '{indicator}' 附近未找到期望值 {expected}"


def score_anchor_accuracy(report: str, required_numbers: Dict[str, dict]) -> dict:
    """
    锚点验证：只检查 independently_verified 的数字。

    关键改进 (V9.0.1): 做指标-数值关联验证，而非简单的数字集合包含。
    必须验证数字出现在对应指标名附近（150字符窗口内），防止张冠李戴。
    """
    anchors = {k: v for k, v in required_numbers.items()
               if v.get("source") == "independently_verified"}

    if not anchors:
        return {"accuracy": 1.0, "matched": [], "mismatched": [],
                "total": 0, "is_anchor_test": False}

    matched, mismatched = [], []
    for key, spec in anchors.items():
        indicator = _extract_indicator_name(key)
        expected = spec["value"]
        tolerance = spec.get("tolerance_pct", 3) / 100.0

        found, detail = _check_indicator_number_association(
            report, indicator, expected, tolerance)

        if found:
            matched.append(key)
        else:
            mismatched.append({"key": key, "indicator": indicator,
                               "expected": expected, "detail": detail})

    total = len(matched) + len(mismatched)
    accuracy = len(matched) / total if total > 0 else 1.0
    return {
        "accuracy": round(accuracy, 4),
        "matched": matched,
        "mismatched": mismatched,
        "total": total,
        "is_anchor_test": True,
        "alert": f"⚠️ 锚点失败({len(mismatched)}个): {[m['indicator'] for m in mismatched]}" if mismatched else "✅ 锚点全部通过",
    }


def score_number_accuracy(report: str, required_numbers: Dict[str, dict],
                          data_values: dict = None) -> dict:
    """
    数值准确性：检查所有 required_numbers 是否在报告中与对应指标关联出现。

    关键改进 (V9.0.1): 做指标-数值关联验证，不再做盲目的数字集合包含匹配。
    """
    if not required_numbers:
        return {"accuracy": 1.0, "matched": [], "mismatched": [],
                "total": 0, "anchors_only": False}

    matched, mismatched = [], []
    for key, spec in required_numbers.items():
        indicator = _extract_indicator_name(key)
        expected = spec["value"]
        tolerance = spec.get("tolerance_pct", 3) / 100.0

        found, detail = _check_indicator_number_association(
            report, indicator, expected, tolerance)

        if found:
            matched.append(key)
        else:
            mismatched.append({"key": key, "indicator": indicator,
                               "expected": expected, "detail": detail})

    total = len(matched) + len(mismatched)
    accuracy = len(matched) / total if total > 0 else 1.0
    return {
        "accuracy": round(accuracy, 4),
        "matched": matched,
        "mismatched": mismatched,
        "total": total,
        "anchors_only": False,
    }


def score_traceability(report: str, task_results: list) -> dict:
    """
    数据溯源率：检查报告中可追溯到 SQL 查询的数据点占比。

    V9.0.1 修复: 统计所有数据点（含无 source 标注的），
    而非只统计有 sources 的。通过 task_results 中的 data 字段推断数据总量。
    """
    if not task_results:
        return {"rate": 1.0, "traced": 0, "untraced": 0,
                "by_source": {}, "reason": "无数据任务"}

    all_sources = {}
    total_data_points = 0  # 所有数据点

    for r in task_results:
        if not r.get("success", True):
            continue
        if r.get("task_type") != "data_query":
            continue
        data = r.get("data", {})
        if not isinstance(data, dict):
            continue
        inner = data.get("data", {})
        if isinstance(inner, dict):
            # 统计 data 中的数值型键
            for k, v in inner.items():
                if isinstance(v, (int, float)):
                    if k in ("found", "success", "confidence", "source"):
                        continue
                    total_data_points += 1

        # 收集 sources
        sources = data.get("sources", {})
        if sources:
            all_sources.update(sources)

    if total_data_points == 0:
        return {"rate": 1.0, "traced": 0, "untraced": 0,
                "by_source": {}, "reason": "无数据点"}

    # 分类统计
    by_source = defaultdict(int)
    traced_count = len(all_sources)

    for key, src in all_sources.items():
        if src == "sql":
            by_source["sql"] += 1
        elif "fallback" in src:
            by_source["fallback"] += 1
        elif "computed" in src:
            by_source["computed"] += 1
        else:
            by_source["other"] += 1

    untraced = max(0, total_data_points - traced_count)
    sql_direct = by_source.get("sql", 0)
    # 溯源率 = 有来源的数据点 / 总数据点
    rate = traced_count / total_data_points

    return {
        "rate": round(rate, 4),
        "traced": traced_count,
        "untraced": untraced,
        "total_data_points": total_data_points,
        "by_source": dict(by_source),
        "sql_direct_pct": round(sql_direct / max(total_data_points, 1) * 100, 1),
        "detail": f"SQL直查 {sql_direct}/{total_data_points} ({sql_direct/max(total_data_points,1)*100:.0f}%), "
                  f"回退 {by_source.get('fallback', 0)}, 计算 {by_source.get('computed', 0)}, "
                  f"无溯源 {untraced}",
    }


def score_chart_render_rate(results: list, expected_chart: str = None) -> dict:
    """
    图表渲染率：检查是否成功生成了图表。

    返回实际生成的图表数量、类型，以及与期望的对比。
    """
    charts_generated = []
    for r in results:
        if not r.get("success", True):
            continue
        if r.get("task_type") == "chart":
            chart_data = r.get("data", {})
            if isinstance(chart_data, dict) and chart_data:
                chart_type = chart_data.get("type", chart_data.get("chart_type", "unknown"))
                has_data = bool(chart_data.get("series") or chart_data.get("data"))
                charts_generated.append({
                    "type": chart_type,
                    "has_data": has_data,
                    "skip_reason": chart_data.get("skip_reason", ""),
                })

    total = len(charts_generated)
    valid = sum(1 for c in charts_generated if c["has_data"])
    rate = valid / total if total > 0 else (0.0 if expected_chart else 1.0)

    return {
        "rate": round(rate, 4),
        "total": total,
        "valid": valid,
        "expected": expected_chart is not None,
        "charts": charts_generated,
        "detail": f"{valid}/{total} 图表有数据",
    }


def score_structural_coverage(report: str, expected_dimensions: list) -> dict:
    """
    结构覆盖度：检查报告是否覆盖了期望的分析维度。

    V9.0.1: 改进匹配逻辑 — 关键词拆分+语义关联，不再纯子串匹配。
    "杜邦分解" 应匹配 "杜邦分析"、"ROE_2024" 应匹配 "ROE"。
    避免 "对比" 这种短词产生假阳性（需上下文验证）。
    """
    if not expected_dimensions:
        return {"coverage": 1.0, "found": [], "missing": [], "total": 0}

    # 维度名拆分扩展 — 用于模糊匹配
    def expand_dimension(dim: str) -> list:
        """将维度名拆分为可匹配的词元列表。"""
        tokens = []
        # 去掉年份后缀和下划线
        clean = dim.replace("_", " ").replace("(", " ").replace(")", " ")
        tokens.append(clean.strip())

        # 拆分复合词
        # "ROE_2024" → ["ROE", "2024", "ROE_2024"]
        parts = re.split(r'[_()（）\s]+', dim)
        for p in parts:
            if p.strip():
                tokens.append(p.strip())

        # 常见同义映射
        synonyms = {
            "杜邦分解": ["杜邦分析", "杜邦"],
            "对比": ["vs", "VS", "比较", "对比分析"],
            "打分": ["评分", "评级", "评估"],
        }
        for k, vs in synonyms.items():
            if k in dim:
                tokens.extend(vs)

        return list(set(tokens))

    report_lower = report.lower()
    found, missing = [], []

    for dim in expected_dimensions:
        tokens = expand_dimension(dim)
        matched = False

        for token in tokens:
            token_lower = token.lower()
            if token_lower in report_lower or token in report:
                matched = True
                break

        # 特殊处理：短词如"对比"、"盈利"等，需要更多上下文验证
        # 如果只有短词匹配，检查附近是否有相关财务术语
        if not matched and len(dim) <= 3:
            # 对短维度名，放宽到检查是否作为独立概念出现
            # 而不是作为子串出现（"对比" ⊂ "相比之下" 应该通过）
            if re.search(rf'\b{re.escape(dim)}\b', report):
                matched = True

        if matched:
            found.append(dim)
        else:
            missing.append(dim)

    coverage = len(found) / len(expected_dimensions) if expected_dimensions else 1.0
    return {
        "coverage": round(coverage, 4),
        "found": found,
        "missing": missing,
        "total": len(expected_dimensions),
    }


def score_hallucination(report: str, data_values: dict) -> dict:
    """
    幻觉检测：检查报告中的方向性断言是否与数据一致。

    例如报告说"毛利率同比下降"，检查数据是否确实下降。
    """
    if not data_values or not report:
        return {"score": 1.0, "checked": 0, "hallucinations": [],
                "reason": "无数据可校验"}

    direction_patterns = [
        (r'(毛利率|净利率|ROE|ROA|资产负债率|负债率|营收|收入|净利润|现金流|费用|成本)'
         r'.{0,15}(下降|下滑|减少|降低|回落|下跌|缩水)', "下降"),
        (r'(毛利率|净利率|ROE|ROA|资产负债率|负债率|营收|收入|净利润|现金流|费用|成本)'
         r'.{0,15}(上升|增长|提高|增加|提升|扩大|上涨)', "上升"),
        (r'(下降|下滑|减少|降低|回落|下跌)'
         r'.{0,15}(毛利率|净利率|ROE|ROA|资产负债率|负债率|营收|收入|净利润|现金流|费用|成本)', "下降"),
        (r'(上升|增长|提高|增加|提升|扩大|上涨)'
         r'.{0,15}(毛利率|净利率|ROE|ROA|资产负债率|负债率|营收|收入|净利润|现金流|费用|成本)', "上升"),
    ]

    # 从 data_values 推断实际方向
    indicator_years = {}
    for key, val in data_values.items():
        parts = key.rsplit("_", 1)
        if len(parts) == 2:
            indicator, year_str = parts[0], parts[1]
        else:
            continue
        try:
            year = int(year_str)
            if 2000 <= year <= 2030:
                indicator_years.setdefault(indicator, {})[year] = val
        except ValueError:
            continue

    actual_directions = {}
    for indicator, year_vals in indicator_years.items():
        years = sorted(year_vals.keys())
        if len(years) >= 2:
            latest, prev = years[-1], years[-2]
            change = year_vals[latest] - year_vals[prev]
            prev_val = year_vals[prev]
            if prev_val != 0:
                pct = change / abs(prev_val) * 100
                if pct > 1:
                    actual_directions[indicator] = ("上升", pct)
                elif pct < -1:
                    actual_directions[indicator] = ("下降", abs(pct))

    checked = 0
    hallucinations = []
    seen_texts = set()

    for pattern, claimed_dir in direction_patterns:
        for m in re.finditer(pattern, report):
            matched_text = m.group(0)
            if matched_text in seen_texts:
                continue
            seen_texts.add(matched_text)

            indicator = None
            for ind in actual_directions:
                if ind in matched_text:
                    indicator = ind; break
            if indicator is None:
                continue

            actual_dir, actual_pct = actual_directions[indicator]
            checked += 1
            if claimed_dir != actual_dir:
                hallucinations.append({
                    "text": matched_text[:60],
                    "indicator": indicator,
                    "claimed": claimed_dir,
                    "actual": actual_dir,
                    "actual_change_pct": round(actual_pct, 1),
                })

    score = 1.0 - len(hallucinations) / max(checked, 1)
    return {
        "score": round(score, 4),
        "checked": checked,
        "hallucinations": hallucinations,
        "indicator_count": len(actual_directions),
    }


def score_industry_benchmark(report: str, benchmark_key: str = None,
                             benchmarks: dict = None) -> dict:
    """
    行业基准引用：检查报告是否引用了行业平均水平进行对比。

    benchmarks 来自 meta.industry_benchmarks。
    """
    if not benchmark_key or not benchmarks:
        return {"used": False, "rate": 1.0, "reason": "无行业基准要求"}

    industry = benchmarks.get(benchmark_key, {})
    if not industry:
        return {"used": False, "rate": 1.0, "reason": f"未找到行业 '{benchmark_key}' 的基准数据"}

    # 检查报告中是否提及行业对比
    industry_keywords = ["行业平均", "行业均值", "行业中位", "同业", "行业对比", "行业水平"]
    has_reference = any(kw in report for kw in industry_keywords)

    # 检查是否引用了具体的行业基准数值
    referenced_values = []
    for metric, value in industry.items():
        if str(value)[:4] in report:
            referenced_values.append(metric)

    return {
        "used": has_reference or len(referenced_values) > 0,
        "rate": 1.0 if has_reference else 0.5 if referenced_values else 0.0,
        "referenced_metrics": referenced_values,
        "has_explicit_comparison": has_reference,
        "industry": benchmark_key,
    }


def extract_data_values_from_results(results: list) -> dict:
    """从 Agent 执行结果中提取原始数据值。"""
    data_values = {}
    for r in results:
        if not r.get("success", True) or r.get("task_type") != "data_query":
            continue
        data = r.get("data", {})
        if not isinstance(data, dict):
            continue
        inner = data.get("data", {})
        if isinstance(inner, dict):
            for k, v in inner.items():
                if isinstance(v, (int, float)):
                    if k in ("found", "success", "confidence", "source"):
                        continue
                    data_values[k] = v
    return data_values


# ════════════════════════════════════════════════════════════════
# 综合评分计算
# ════════════════════════════════════════════════════════════════

def compute_overall_score(scores: dict, is_template: bool) -> float:
    """根据题目类型选择合适的权重计算综合得分。"""
    weights = TEMPLATE_WEIGHTS if is_template else FREEFORM_WEIGHTS

    overall = 0.0
    total_weight = 0.0
    for key, weight in weights.items():
        if key in scores:
            overall += scores[key] * weight
            total_weight += weight

    return round(overall / total_weight, 4) if total_weight > 0 else 0.0


# ════════════════════════════════════════════════════════════════
# 主评测流程
# ════════════════════════════════════════════════════════════════

def run_benchmark(questions: List[dict], meta: dict) -> dict:
    """执行全量评测，返回结构化结果。"""
    planner = Planner()
    n = len(questions)

    # 累计器
    accum = {
        "anchor": [], "number": [], "traceability": [], "chart": [],
        "structural": [], "hallucination": [], "industry": [],
        "overall_scores": [], "latencies": [], "tokens": [], "costs": [],
    }

    # 分组累计
    rag_accum = defaultdict(lambda: defaultdict(list))     # rag_accum["RAG"]["anchor"] = [...]
    nonrag_accum = defaultdict(lambda: defaultdict(list))

    results_detail = []
    failed = []
    start_all = time.time()
    clarification_count = 0

    for i, q in enumerate(questions, 1):
        qid = q.get("id", f"Q{i}")
        cat = q.get("category", "unknown")
        diff = q.get("difficulty", "unknown")
        query = q.get("query", "")
        has_rag = q.get("has_rag", False)
        is_template = q.get("template", "") != "" and q.get("category") != "自由拆解"

        logger.info(f"\n{'='*50}")
        logger.info(f"[{i}/{n}] {qid} [{cat}][{diff}] {'RAG' if has_rag else 'SQL'} | {query[:70]}...")

        # Phase 1: Planner
        plan_start = time.time()
        try:
            plan = planner.plan(query)
        except Exception as e:
            logger.error(f"  Planner 失败: {e}")
            failed.append({"id": qid, "phase": "planner", "error": str(e)})
            continue
        plan_time = time.time() - plan_start

        if plan.requires_clarification:
            clarification_count += 1
            logger.warning(f"  [!] 需要追问: {plan.requires_clarification[:80]}")

        # Phase 2: 全链路执行
        exec_start = time.time()
        try:
            agent_result = run_agent_sync(query, plan=plan)
            usage = get_usage()
            question_tokens = usage.get("total_tokens", 0)
            question_cost = round(
                (usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0))
                / 1_000_000 * 2.0, 6,
            )
        except Exception as e:
            logger.error(f"  Agent 执行失败: {e}")
            failed.append({"id": qid, "phase": "executor", "error": str(e)})
            continue
        exec_time = time.time() - exec_start

        # Phase 3: 多维度评分
        report = agent_result.get("report", "")
        task_results = agent_result.get("task_results", [])
        data_values = extract_data_values_from_results(task_results)
        required_nums = normalize_required_numbers(q)

        # 各项评分
        anchor_result = score_anchor_accuracy(report, required_nums)
        number_result = score_number_accuracy(report, required_nums, data_values)
        trace_result = score_traceability(report, task_results)
        chart_result = score_chart_render_rate(task_results, q.get("required_chart"))
        structural_result = score_structural_coverage(
            report, q.get("expected_dimensions", [])
        )
        halluc_result = score_hallucination(report, data_values)
        industry_result = score_industry_benchmark(
            report,
            q.get("industry_benchmark"),
            meta.get("industry_benchmarks", {}),
        )

        # ── S6 修复: min_tasks 惩罚 ──
        min_tasks = q.get("min_tasks", 0)
        actual_tasks = len(plan.tasks)
        task_count_penalty = 1.0
        if min_tasks > 0 and actual_tasks < min_tasks:
            task_count_penalty = actual_tasks / min_tasks
            logger.warning(f"  ⚠️ 任务数不足: {actual_tasks}/{min_tasks} (惩罚系数 {task_count_penalty:.2f})")

        # 汇总单题得分
        scores = {
            "anchor_accuracy": anchor_result["accuracy"],
            "number_accuracy": number_result["accuracy"],
            "traceability_rate": trace_result["rate"],
            "chart_render_rate": chart_result["rate"],
            "structural_coverage": structural_result["coverage"],
            "hallucination_score": halluc_result["score"],
            "industry_benchmark": industry_result["rate"],
        }
        overall = compute_overall_score(scores, is_template) * task_count_penalty

        # 累计
        accum["anchor"].append(anchor_result["accuracy"])
        accum["number"].append(number_result["accuracy"])
        accum["traceability"].append(trace_result["rate"])
        accum["chart"].append(chart_result["rate"])
        accum["structural"].append(structural_result["coverage"])
        accum["hallucination"].append(halluc_result["score"])
        accum["industry"].append(industry_result["rate"])
        accum["overall_scores"].append(overall)
        accum["latencies"].append(exec_time)
        accum["tokens"].append(question_tokens)
        accum["costs"].append(question_cost)

        # 按公司分离累计
        group = rag_accum if has_rag else nonrag_accum
        for key, val in scores.items():
            group[key].append(val)
        group["overall"].append(overall)
        group["latency"].append(exec_time)

        # 日志
        logger.info(
            f"  ⏱ {exec_time:.1f}s | 📊 综合={overall:.1%} | "
            f"锚点={anchor_result['accuracy']:.1%} | 数值={number_result['accuracy']:.1%} | "
            f"溯源={trace_result['rate']:.1%} | 图表={chart_result['rate']:.1%}"
        )
        if anchor_result.get("mismatched"):
            logger.warning(f"  ⚠️ 锚点失败: {anchor_result['mismatched']}")
        if halluc_result.get("hallucinations"):
            for h in halluc_result["hallucinations"][:3]:
                logger.warning(f"  ⚠️ 幻觉: {h['text']} (声称{h['claimed']}, 实际{h['actual']})")

        # 保存详情
        results_detail.append({
            "id": qid,
            "query": query[:100],
            "category": cat,
            "difficulty": diff,
            "has_rag": has_rag,
            "is_template": is_template,
            "company": q.get("company", ""),
            "template": q.get("template", ""),
            "scores": scores,
            "overall": overall,
            "plan_time_s": round(plan_time, 2),
            "exec_time_s": round(exec_time, 2),
            "task_count": len(plan.tasks),
            "clarification": plan.requires_clarification if plan.requires_clarification else None,
            "tokens": question_tokens,
            "cost_rmb": question_cost,
            "anchor_detail": anchor_result,
            "number_detail": number_result,
            "trace_detail": trace_result,
            "chart_detail": chart_result,
            "structural_detail": structural_result,
            "hallucination_detail": halluc_result,
            "industry_detail": industry_result,
        })

    elapsed = time.time() - start_all

    # ── 计算汇总统计 ──
    def avg(lst, default=0.0):
        return round(sum(lst) / len(lst), 4) if lst else default

    # RAG vs 非RAG 统计
    def group_stats(gdict):
        return {
            key: {
                "mean": avg(vals), "count": len(vals),
                "min": round(min(vals), 4) if vals else 0,
                "max": round(max(vals), 4) if vals else 0,
            }
            for key, vals in gdict.items() if vals
        }

    summary = {
        "timestamp": datetime.now().isoformat(),
        "dataset": meta.get("name", "unknown"),
        "total_questions": n,
        "completed": n - len(failed),
        "failed": len(failed),
        "clarification_needed": clarification_count,
        "elapsed_s": round(elapsed, 1),

        # 全局平均
        "scores": {
            "anchor_accuracy": avg(accum["anchor"]),
            "number_accuracy": avg(accum["number"]),
            "traceability_rate": avg(accum["traceability"]),
            "chart_render_rate": avg(accum["chart"]),
            "structural_coverage": avg(accum["structural"]),
            "hallucination_score": avg(accum["hallucination"]),
            "industry_benchmark": avg(accum["industry"]),
            "overall": avg(accum["overall_scores"]),
        },

        # RAG vs 非RAG
        "rag_companies": group_stats(rag_accum),
        "non_rag_companies": group_stats(nonrag_accum),

        # 性能 & 成本
        "performance": {
            "avg_latency_s": avg(accum["latencies"]),
            "min_latency_s": round(min(accum["latencies"]), 1) if accum["latencies"] else 0,
            "max_latency_s": round(max(accum["latencies"]), 1) if accum["latencies"] else 0,
            "total_tokens": sum(accum["tokens"]),
            "total_cost_rmb": round(sum(accum["costs"]), 4),
            "avg_cost_rmb": avg(accum["costs"]),
        },

        # 目标对比
        "vs_targets": {},
    }

    # 对比生产级目标
    for key, target in PRODUCTION_TARGETS.items():
        if key in summary["scores"]:
            actual = summary["scores"][key]
            summary["vs_targets"][key] = {
                "actual": actual,
                "target": target,
                "pass": actual >= target,
                "gap": round(target - actual, 4) if actual < target else 0,
            }
    # 延迟特殊处理: 混合场景用自由拆解目标(更宽松)
    avg_lat = summary["performance"]["avg_latency_s"]
    latency_target = PRODUCTION_TARGETS["avg_latency_freeform_s"]
    summary["vs_targets"]["avg_latency_s"] = {
        "actual": avg_lat,
        "target": latency_target,
        "pass": avg_lat <= latency_target,
        "gap": round(avg_lat - latency_target, 1),
        "note": f"混合场景使用自由拆解目标 {latency_target}s",
    }

    return {
        "summary": summary,
        "details": results_detail,
        "failed": failed,
    }


# ════════════════════════════════════════════════════════════════
# 报告输出
# ════════════════════════════════════════════════════════════════

def print_report(result: dict):
    """打印人类可读的评测报告。"""
    s = result["summary"]
    scores = s["scores"]
    perf = s["performance"]
    targets = s["vs_targets"]

    def check(actual, target, higher_better=True):
        if higher_better:
            return "✅" if actual >= target else "❌"
        return "✅" if actual <= target else "❌"

    print("\n" + "=" * 75)
    print("  V9.0 Agent 评测报告 — 生产级质量门禁")
    print("=" * 75)
    print(f"  评测集: {s['dataset']}")
    print(f"  完成: {s['completed']}/{s['total_questions']} | "
          f"失败: {s['failed']} | 追问: {s['clarification_needed']} | "
          f"耗时: {s['elapsed_s']:.0f}s")
    if LIGHT_MODE:
        print("  ⚡ 轻量模式 (CrossEncoder 跳过)")
    print()

    # 核心指标
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │  核心质量指标                   实际     目标   门禁 │")
    print("  ├─────────────────────────────────────────────────────┤")
    rows = [
        ("🔴 锚点准确率 (独立验证)", "anchor_accuracy", True),
        ("📊 数值准确率 (全量)", "number_accuracy", True),
        ("🔍 数据溯源率 (SQL直查占比)", "traceability_rate", True),
        ("📈 图表渲染率", "chart_render_rate", True),
        ("🏗️ 结构覆盖度 (自由拆解)", "structural_coverage", True),
        ("🔬 幻觉检测", "hallucination_score", True),
        ("🏭 行业基准引用", "industry_benchmark", True),
    ]
    for label, key, higher_better in rows:
        actual = scores.get(key, 0)
        target = PRODUCTION_TARGETS.get(key, 0)
        print(f"  │ {label:24s} {actual:7.1%}  {target:7.0%}   {check(actual, target, higher_better)} │")
    print("  ├─────────────────────────────────────────────────────┤")
    overall = scores.get("overall", 0)
    target = PRODUCTION_TARGETS["overall_score"]
    print(f"  │ {'⭐ 综合评分':26s} {overall:7.1%}  {target:7.0%}   {check(overall, target)} │")
    print("  └─────────────────────────────────────────────────────┘")
    print()

    # 性能
    print(f"  ⚡ 平均延迟: {perf['avg_latency_s']:.1f}s "
          f"(模板<{PRODUCTION_TARGETS['avg_latency_template_s']}s, "
          f"自由<{PRODUCTION_TARGETS['avg_latency_freeform_s']}s)")
    print(f"  💰 总费用: ¥{perf['total_cost_rmb']:.4f} | "
          f"单题均费: ¥{perf['avg_cost_rmb']:.4f} | "
          f"总Token: {perf['total_tokens']:,}")
    print()

    # RAG vs 非RAG 对比
    rag = s.get("rag_companies", {})
    nonrag = s.get("non_rag_companies", {})
    if rag and nonrag:
        print("  ┌────────────────── RAG vs 非RAG 对比 ──────────────┐")
        print("  │ 维度                RAG(有年报)    非RAG(仅SQL)  差距 │")
        print("  ├────────────────────────────────────────────────────┤")
        key_dimensions = [
            ("综合评分", "overall"),
            ("锚点准确率", "anchor_accuracy"),
            ("数值准确率", "number_accuracy"),
            ("溯源率", "traceability_rate"),
            ("结构覆盖", "structural_coverage"),
            ("幻觉检测", "hallucination_score"),
        ]
        for label, key in key_dimensions:
            r_val = rag.get(key, {}).get("mean", 0)
            n_val = nonrag.get(key, {}).get("mean", 0)
            diff = r_val - n_val
            sign = "+" if diff > 0 else ""
            print(f"  │ {label:14s} {r_val:12.1%} {n_val:12.1%} {sign}{diff:+.1%} │")
        print("  └────────────────────────────────────────────────────┘")

    # 未达标项
    failing = [(k, v) for k, v in targets.items() if not v["pass"]]
    if failing:
        print(f"\n  ⚠️ 未达标项 ({len(failing)}):")
        for key, v in failing:
            print(f"     - {key}: {v['actual']:.1%} (目标 {v['target']:.0%}, 差距 {v['gap']:.1%})")

    # 失败详情
    if result["failed"]:
        print(f"\n  ❌ 失败题目:")
        for f in result["failed"]:
            print(f"     - {f['id']}: {f['phase']} — {f['error']}")

    print()


def save_report(result: dict, dataset: str = "v9"):
    """持久化评测报告。"""
    reports_dir = Path(__file__).parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports_dir / f"agent_bench_v9_{dataset}_{timestamp}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"📄 报告已保存: {path}")

    # 更新趋势文件
    trend_path = reports_dir / "v9_trend.json"
    trend_data = []
    if trend_path.exists():
        with open(trend_path, "r", encoding="utf-8") as f:
            trend_data = json.load(f)

    trend_data.append({
        "timestamp": result["summary"]["timestamp"],
        "overall": result["summary"]["scores"]["overall"],
        "anchor_accuracy": result["summary"]["scores"]["anchor_accuracy"],
        "number_accuracy": result["summary"]["scores"]["number_accuracy"],
        "avg_latency_s": result["summary"]["performance"]["avg_latency_s"],
        "total_cost_rmb": result["summary"]["performance"]["total_cost_rmb"],
        "completed": result["summary"]["completed"],
    })

    with open(trend_path, "w", encoding="utf-8") as f:
        json.dump(trend_data, f, ensure_ascii=False, indent=2)

    print(f"📈 趋势已更新: {trend_path} ({len(trend_data)} 次记录)")


# ════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="V9.0 Agent 评测")
    parser.add_argument("--dataset", choices=["v9", "v8"], default="v9",
                        help="评测集: v9 (50题) 或 v8 (15题)")
    parser.add_argument("--quick", action="store_true",
                        help="快速模式：只跑前5题")
    parser.add_argument("--dry-run", action="store_true",
                        help="空跑模式：只加载题目不执行")
    args = parser.parse_args()

    questions, meta = load_questions(args.dataset)

    if args.quick:
        questions = questions[:5]
        logger.info(f"快速模式: 只评测前 {len(questions)} 题")

    if args.dry_run:
        logger.info("空跑模式 — 只验证题目加载")
        for q in questions:
            required = normalize_required_numbers(q)
            anchors = sum(1 for v in required.values()
                         if v.get("source") == "independently_verified")
            print(f"  {q['id']:8s} [{q.get('difficulty','?'):6s}] "
                  f"RAG={q.get('has_rag',False)} "
                  f"anchors={anchors} "
                  f"query={q['query'][:60]}...")
        return

    logger.info(f"开始 V9.0 全量评测: {len(questions)} 题")
    result = run_benchmark(questions, meta)
    print_report(result)
    save_report(result, args.dataset)

    # 返回退出码（门禁）
    overall = result["summary"]["scores"]["overall"]
    if overall < PRODUCTION_TARGETS["overall_score"]:
        logger.warning(f"综合评分 {overall:.1%} 未达生产级目标 {PRODUCTION_TARGETS['overall_score']:.0%}")
        sys.exit(1)
    else:
        logger.info(f"✅ 综合评分 {overall:.1%} 达生产级目标")


if __name__ == "__main__":
    main()
