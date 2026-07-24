"""
图表生成工具 — 生成 ECharts option JSON，前端直接渲染

支持 5 种图表类型：
- line: 折线图（趋势分析）— 面积渐变 + 平滑曲线
- bar: 柱状图（对比分析）— 圆角 + 渐变色
- pie: 饼图/环形图（结构分析）— 扇区圆角 + 阴影
- radar: 雷达图（多维度评估）
- dual_axis: 双轴图（柱状+折线）— 营收+增速经典组合

V8.3: 从 matplotlib 静态 PNG 迁移到 ECharts 前端渲染。
不再依赖 matplotlib，直接输出 ECharts option JSON 字典。
"""

from typing import Dict, Any, Optional, List
from loguru import logger

from agent.schemas import ChartConfig


# ==================== 现代 10 色调色板 ====================
CHART_COLORS = [
    '#4f46e5',  # Indigo 靛蓝
    '#10b981',  # Emerald 翠绿
    '#f59e0b',  # Amber 琥珀
    '#ef4444',  # Red 红
    '#8b5cf6',  # Purple 紫
    '#ec4899',  # Pink 粉
    '#06b6d4',  # Cyan 青
    '#84cc16',  # Lime 柠檬绿
    '#f97316',  # Orange 橙
    '#6366f1',  # Violet 蓝紫
]

SERIES_COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
                 '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1']


def _build_chart_description(labels: List, values: List) -> str:
    """生成人类可读的图表数据摘要"""
    if labels and values:
        return '、'.join([f'{l}: {v}' for l, v in zip(labels, values)])
    return ''


# ==================== 工具函数 ====================

def _linear_gradient(color: str, direction: str = 'bottom',
                     stops: List[Dict] = None) -> Dict:
    """生成 ECharts linear 渐变配置"""
    x, y, x2, y2 = 0, 0, 0, 1  # 默认从上到下
    if direction == 'top':
        x, y, x2, y2 = 0, 1, 0, 0
    elif direction == 'right':
        x, y, x2, y2 = 0, 0, 1, 0

    if stops is None:
        stops = [
            {'offset': 0, 'color': color},
            {'offset': 1, 'color': color + 'cc'},  # 80% 透明度
        ]

    return {
        'type': 'linear',
        'x': x, 'y': y, 'x2': x2, 'y2': y2,
        'colorStops': stops,
    }


def _area_gradient(color: str) -> Dict:
    """生成面积渐变（从 40% 透明度到 5% 透明度）"""
    return {
        'type': 'linear',
        'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
        'colorStops': [
            {'offset': 0, 'color': color + '66'},   # 40% opacity
            {'offset': 1, 'color': color + '0D'},   # 5% opacity
        ],
    }


def _base_title(title: str) -> Dict:
    """统一标题样式"""
    return {
        'text': title,
        'left': 'center',
        'top': 10,
        'textStyle': {
            'fontSize': 16,
            'fontWeight': 600,
            'color': '#1e293b',
        },
    }


def _base_tooltip(trigger: str = 'axis') -> Dict:
    """统一 tooltip 样式 — 白色悬浮卡 + 阴影"""
    return {
        'trigger': trigger,
        'backgroundColor': 'rgba(255, 255, 255, 0.95)',
        'borderColor': '#e2e8f0',
        'borderWidth': 1,
        'textStyle': {'color': '#334155', 'fontSize': 13},
        'extraCssText': 'border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);',
    }


def _base_grid() -> Dict:
    """统一 grid 布局"""
    return {
        'left': '5%',
        'right': '8%',
        'bottom': '18%',
        'top': '22%',
        'containLabel': True,
    }


def _base_legend() -> Dict:
    """统一图例样式"""
    return {
        'orient': 'horizontal',
        'bottom': 0,
        'textStyle': {'color': '#64748b', 'fontSize': 12},
        'itemWidth': 12,
        'itemHeight': 12,
    }


def _format_labels(labels: List, max_len: int = 8) -> List[str]:
    """截断过长的标签并添加省略号"""
    result = []
    for label in labels:
        s = str(label)
        if len(s) > max_len:
            s = s[:max_len] + '..'
        result.append(s)
    return result


def _should_show_label(data_len: int) -> bool:
    """数据点 <= 15 时显示数据标签"""
    return data_len <= 15


# ==================== ChartTool 类 ====================

class ChartTool:
    """
    财务图表生成工具（ECharts 版）。

    用法:
        tool = ChartTool()
        result = tool.run(
            chart_type="line",
            title="茅台近三年毛利率趋势",
            data={"labels": ["2022","2023","2024"], "values": [92.0, 91.8, 91.5]},
        )
        # result = {"chart_option": {...}}  — 前端直接 echarts.setOption()

    V8.3 重构: 从 matplotlib PNG → ECharts option JSON
    """

    def __init__(self, output_dir: str = None):
        self.name = "chart"
        # output_dir 保留参数，ECharts 模式下不需要

    def run(self, chart_type: str = "auto", title: str = "财务分析图表",
            data: dict = None, x_label: str = "", y_label: str = "",
            _skip_multi: bool = False,  # V8.5: 防止 generate_multi → run → generate_multi 无限递归
            **kwargs) -> Dict[str, Any]:
        """
        生成 ECharts option 并返回。V8.4: 自主决策图表类型 + 多图互补。

        V8.4: 指标 >5 时自动调用 generate_multi 生成多张互补图表。
        返回单图: {"chart_option": ..., "chart_description": ...}
        返回多图: {"chart_options": [...], "chart_descriptions": [...], "chart_count": N}
        """
        if data is None:
            data = {}

        # 合并 kwargs 中的数值参数到 data
        # V9.0: 过滤技术键（英文指标名/元数据键），只保留可用于图表展示的标签
        _SKIP_CHART_KEYS = {"result", "confidence", "success", "source", "found",
                           "chart_type", "title", "x_label", "y_label"}
        numeric_all = {k: v for k, v in {**kwargs, **data}.items()
                      if isinstance(v, (int, float)) and k not in _SKIP_CHART_KEYS}
        # P2修复: 接受英文键名, 通过 _CN_LABEL_FALLBACK 转中文
        numeric_extra = {}
        for k, v in numeric_all.items():
            has_cjk = any('一' <= c <= '鿿' for c in str(k))
            is_eng_metric = str(k).replace('_', '').isascii() and str(k).islower()
            if has_cjk or not is_eng_metric:
                numeric_extra[k] = v
            elif is_eng_metric:
                # 英文键名(如 revenue_2024) → 查 _CN_LABEL_FALLBACK 转中文
                base = str(k).rsplit('_', 1)[0]  # 去年份后缀
                cn = ChartTool._CN_LABEL_FALLBACK.get(base, '')
                if cn:
                    numeric_extra[cn] = v
        if numeric_extra and not data.get("values") and not data.get("labels"):
            # 去重：同一数值只保留第一个标签（通常是中文display_name）
            seen_vals = set()
            unique_labels, unique_values = [], []
            for k, v in numeric_extra.items():
                if v not in seen_vals:
                    seen_vals.add(v)
                    unique_labels.append(k)
                    unique_values.append(v)
            data["labels"] = unique_labels
            data["values"] = unique_values

        # ── V9.0: 零空白防线 — 数据不足时不生成空白图表 ──
        if not data.get("labels") or not data.get("values"):
            return {
                "chart_option": None,
                "chart_description": "数据不足，无法生成图表。请确认查询参数是否正确。",
                "skip": True,
                "skip_reason": "empty_data",
            }
        if len(data.get("labels", [])) <= 1 or len(data.get("values", [])) <= 1:
            return {
                "chart_option": None,
                "chart_description": f"仅{len(data.get('values',[]))}个可用数据点，不足以生成有意义的图表，以下为数据表格形式展示。",
                "skip": True,
                "skip_reason": "insufficient_data",
                "fallback_table": {"labels": data.get("labels", []), "values": data.get("values", [])},
            }

        # ── 标签中文化（剥离年份后缀 + 去重）──
        self._ensure_chinese_labels(data)

        # ── V8.5: 指标多 → 多图互补（_skip_multi 防止 generate_multi 内部递归）──
        import re
        if not _skip_multi:
            dim_count = len(set(re.sub(r'_\d{4}$', '', str(l)) for l in data.get("labels", [])))
            if dim_count > 5:
                multi = self.generate_multi(data, title)
                if len(multi) > 1:
                    return {
                        "chart_options": [m.get("chart_option") for m in multi],
                        "chart_descriptions": [m.get("chart_description", "") for m in multi],
                        "chart_count": len(multi),
                    }

        # ── 单片图流程 ──
        rec = self.recommend(data)
        if chart_type == "auto" or not chart_type or chart_type == "bar":
            if rec["confidence"] >= 0.5 or rec["chart_type"] != "bar":
                chart_type = rec["chart_type"]
                logger.info(f"[Chart] 自动选择: {chart_type} ({rec['reason']}, 置信度{rec['confidence']})")
        elif rec["confidence"] >= 0.9 and rec["chart_type"] != chart_type:
            logger.warning(f"[Chart] 覆盖 Planner 建议的 {chart_type} → {rec['chart_type']} ({rec['reason']})")
            chart_type = rec["chart_type"]

        # ── V8.4: 雷达图数据格式转换（flat labels/values → categories/series）──
        if chart_type == "radar" and data.get("labels") and data.get("values") \
                and not data.get("categories") and not data.get("series"):
            data["categories"] = data["labels"]
            data["series"] = {"综合评分" if not data.get("title") else data.get("title", "")[:8]: data["values"]}

        config = ChartConfig(
            chart_type=chart_type,
            title=title,
            data=data,
            x_label=x_label or "指标",
            y_label=y_label or "数值",
        )

        chart_methods = {
            "line": self._line_chart,
            "bar": self._bar_chart,
            "pie": self._pie_chart,
            "radar": self._radar_chart,
            "dual_axis": self._dual_axis_chart,
        }

        method = chart_methods.get(config.chart_type)
        if not method:
            logger.warning(f"不支持的图表类型: {config.chart_type}，回退到柱状图")
            method = self._bar_chart

        try:
            option = method(config)
            labels = data.get("labels", [])
            values = data.get("values", [])
            description = _build_chart_description(labels, values)

            # ── P2-9: 专业财务图表增强 ──
            # 工具箱: 另存为图片 + 数据视图
            option["toolbox"] = {
                "show": True,
                "right": 10, "top": 10,
                "feature": {
                    "saveAsImage": {"title": "保存图片", "pixelRatio": 2},
                    "dataView": {"title": "数据视图", "readOnly": True, "lang": ["数据视图", "关闭", "刷新"]},
                },
            }
            # 十字准线 + 精确 tooltip
            option["tooltip"] = {**option.get("tooltip", {}),
                "trigger": "axis",
                "axisPointer": {"type": "cross", "crossStyle": {"color": "#999"}},
                "valueFormatter": "(value) => typeof value === 'number' ? value.toLocaleString('zh-CN', {maximumFractionDigits: 2}) : value",
            }
            # 时间序列图表加底部缩放滑块
            if option.get("xAxis") and isinstance(option["xAxis"], dict):
                option["dataZoom"] = [{
                    "type": "slider", "start": 0, "end": 100, "height": 20, "bottom": 6,
                    "borderColor": "#e2e8f0", "fillerColor": "rgba(99,102,241,0.1)",
                    "handleStyle": {"color": "#6366f1"},
                }]
            # 图例可点击切换
            if option.get("legend") and isinstance(option["legend"], dict):
                option["legend"]["selectedMode"] = "multiple"
                option["legend"]["inactiveColor"] = "#cbd5e1"

            return {"chart_option": option, "chart_description": description}
        except Exception as e:
            logger.error(f"图表生成失败 [{config.chart_type}]: {e}")
            return {"chart_option": self._error_option(str(e)), "chart_description": ""}

    # ============ V8.4: 图表类型推荐引擎 ============

    def recommend(self, data: dict) -> dict:
        """
        根据数据实际特征自动推荐图表类型。纯规则，零 LLM。

        返回: {"chart_type": str, "reason": str, "confidence": float}
        """
        import re
        numeric_keys = [k for k, v in data.items() if isinstance(v, (int, float))]
        labels = data.get("labels", [])
        values = data.get("values", [])

        if not numeric_keys and not labels:
            return {"chart_type": "bar", "reason": "无特征数据，默认柱状图", "confidence": 0.3}

        # 1. 检测年份后缀 → 时间序列 → 折线图
        year_keys = [k for k in numeric_keys if re.search(r'_\d{4}$', str(k))]
        has_years = len(year_keys) >= 2

        # 2. 提取基础指标名（去年份后缀去重）
        base_metrics = set()
        for k in numeric_keys:
            base = re.sub(r'_\d{4}$', '', str(k))
            base_metrics.add(base)

        # 也检查 labels
        for l in labels:
            base = re.sub(r'_\d{4}$', '', str(l))
            base_metrics.add(base)

        dim_count = len(base_metrics)

        # 3. 检测值域差异（量纲不一致 → 雷达图更合适）
        # V8.5: 财务数据天生不同量纲（营收千亿 vs 增长率%），
        # 若半数以上值为 0-100 范围（百分比/比率类），说明是混合量纲的财务指标集，
        # 此时用柱状图比雷达图更合适（每个柱可以独立标注单位）
        if values and len(values) >= 3:
            abs_vals = [abs(v) for v in values if v != 0]
            if abs_vals and max(abs_vals) / max(min(abs_vals), 0.01) > 10:
                pct_like = sum(1 for v in values if 0 < abs(v) <= 100)
                if pct_like < len(values) * 0.5:
                    return {"chart_type": "radar",
                            "reason": f"{dim_count}个不同量纲指标，雷达图最优",
                            "confidence": 0.85}
                # 否则：混合百分比+大量纲，不适合雷达图，继续往下走到 bar

        # 4. 检测结构占比（values 全正 + sum ≈ 100 → 饼图）
        if values and len(values) <= 6 and all(v > 0 for v in values):
            total = sum(values)
            if 80 < total < 120:
                return {"chart_type": "pie", "reason": "数据呈结构分布特征", "confidence": 0.85}

        # 5. 决策
        if has_years and dim_count == 1:
            return {"chart_type": "line", "reason": "单指标多年趋势", "confidence": 0.95}
        if has_years and dim_count >= 2:
            return {"chart_type": "dual_axis", "reason": "多指标多年趋势，双轴更清晰", "confidence": 0.85}
        if 4 <= dim_count <= 6 and not has_years:
            return {"chart_type": "radar", "reason": f"{dim_count}维度综合评估，雷达图最优", "confidence": 0.90}
        if dim_count > 6 and not has_years:
            return {"chart_type": "bar", "reason": f"{dim_count}维度较多，柱状图更清晰", "confidence": 0.85}
        if dim_count >= 2:
            return {"chart_type": "bar", "reason": "多指标横向对比", "confidence": 0.80}

        return {"chart_type": "bar", "reason": "默认柱状图", "confidence": 0.40}

    @staticmethod
    def _ensure_chinese_labels(data: dict):
        """V8.4: 确保图表标签为中文（剥离年份后缀+task前缀 + 去重），同步去重 values。

        P1-5: 跨公司对比时会产生 "task3_毛利率" / "task4_毛利率" 格式的标签，
        剥离 taskX_ 前缀后转换为 "毛利率(公司A)" / "毛利率(公司B)"。
        """
        import re
        labels = data.get("labels", [])
        values = data.get("values", [])
        if not labels:
            return

        # P1-5: 检测是否有跨公司标签（taskN_ 前缀）
        has_multi_company = any(re.match(r'^task\d+_', str(l)) for l in labels)
        company_labels = {}  # task_id → 公司字母映射

        seen = set()
        clean_labels = []
        clean_values = []
        for i, l in enumerate(labels):
            base = str(l)
            # P1-5: 剥离 task_id 前缀
            task_match = re.match(r'^(task\d+)_(.*)', base)
            if task_match:
                tid, metric = task_match.group(1), task_match.group(2)
                if tid not in company_labels:
                    # 用 A/B/C 命名公司
                    company_labels[tid] = chr(65 + len(company_labels))  # A, B, C...
                company = company_labels[tid]
                base = metric  # 取指标名部分

            # 剥离年份后缀
            base = re.sub(r'_\d{4}$', '', base)
            # 英→中映射兜底
            base = ChartTool._CN_LABEL_FALLBACK.get(base, base)
            # 清理英文缩写：ROE（净资产收益率）→ 净资产收益率
            for eng_prefix, replacement in ChartTool._LABEL_CLEANUP:
                if base.startswith(eng_prefix):
                    base = base[len(eng_prefix):]
                    break
            # 清理残留括号
            base = base.lstrip("（(").rstrip("）)")

            # P1-5: 多公司模式 — 即使净化后同名也保留（加公司后缀区分）
            if has_multi_company and task_match:
                base = f"{base}(公司{company})"

            if base not in seen:
                seen.add(base)
                clean_labels.append(base)
                if i < len(values):
                    clean_values.append(values[i])
        data["labels"] = clean_labels
        data["values"] = clean_values

    # ── 中英文标签兜底映射 ──
    _CN_LABEL_FALLBACK = {
        "revenue": "营业收入", "cost": "营业成本", "net_profit": "净利润",
        "total_assets": "总资产", "equity": "净资产", "total_liabilities": "总负债",
        "current_assets": "流动资产", "current_liabilities": "流动负债",
        "gross_profit_margin": "毛利率", "net_profit_margin": "净利率",
        "roe": "净资产收益率", "roa": "总资产收益率", "debt_ratio": "资产负债率",
        "current_ratio": "流动比率", "quick_ratio": "速动比率",
        "total_asset_turnover": "总资产周转率", "inventory_turnover": "存货周转率",
        "revenue_growth": "营收增长率", "net_profit_growth": "净利润增长率",
        "operating_cf": "经营现金流", "free_cash_flow": "自由现金流",
        "pe_ratio": "市盈率", "pb_ratio": "市净率",
        "cf_to_net_profit": "经营现金流/净利润比率",
        "asset_turnover": "资产周转率", "equity_multiplier": "权益乘数",
    }

    # ── 标签中的英文缩写清理 ──
    _LABEL_CLEANUP = [
        ("ROE（", ""), ("ROA（", ""), ("PE（", ""), ("PB（", ""),
        ("EBITDA（", ""), ("FCF（", ""), ("EPS（", ""),
    ]

    def generate_multi(self, data: dict, title: str = "财务分析") -> List[dict]:
        """
        V8.4: 从同一数据集生成多张互补图表。

        例如: 多维度数据 → 雷达(全景) + 柱状(细节)
        """
        import re
        results = []

        # 主图（_skip_multi=True 防止无限递归）
        main_result = self.run(chart_type="auto", title=title, data=data, _skip_multi=True)
        main_result["chart_description"] = f"主图 · {main_result.get('chart_description', '')}"
        results.append(main_result)

        # 补充图: 数据维度>5 → 加分组柱状图展示细节（_skip_multi=True 防止递归）
        numeric_keys = [k for k, v in data.items() if isinstance(v, (int, float))]
        base_metrics = set()
        for k in numeric_keys:
            base_metrics.add(re.sub(r'_\d{4}$', '', str(k)))

        if len(base_metrics) > 5:
            detail = self.run(chart_type="bar", title=f"{title}（明细）", data=data, _skip_multi=True)
            detail["chart_description"] = "补充 · 各维度详细数值对比"
            results.append(detail)

        return results

    # ============ 折线图 ============

    def _line_chart(self, config: ChartConfig) -> Dict:
        """折线图 — 面积渐变 + 平滑曲线 + 数据标记"""
        data = config.data
        labels = data.get("labels", [])
        values = data.get("values", [])
        series_data = data.get("series", {})

        # 多系列折线图
        if series_data:
            series = []
            for i, (name, vals) in enumerate(series_data.items()):
                color = SERIES_COLORS[i % len(SERIES_COLORS)]
                s = {
                    'name': str(name),
                    'type': 'line',
                    'data': vals,
                    'smooth': True,
                    'smoothMonotone': 'x',
                    'symbol': 'circle',
                    'symbolSize': 6 if len(vals) <= 15 else 4,
                    'lineStyle': {'width': 3, 'color': color},
                    'itemStyle': {'color': color},
                    'areaStyle': {'color': _area_gradient(color)},
                    'emphasis': {'focus': 'series'},
                }
                if _should_show_label(len(vals)):
                    s['label'] = {
                        'show': True, 'position': 'top',
                        'fontSize': 10, 'color': '#64748b',
                    }
                series.append(s)
        else:
            # 单系列折线图
            color = CHART_COLORS[0]
            series = [{
                'name': config.title,
                'type': 'line',
                'data': values,
                'smooth': True,
                'smoothMonotone': 'x',
                'symbol': 'circle',
                'symbolSize': 6 if _should_show_label(len(values)) else 0,
                'lineStyle': {'width': 3, 'color': color},
                'itemStyle': {'color': color},
                'areaStyle': {'color': _area_gradient(color)},
                'emphasis': {'focus': 'series'},
            }]
            if _should_show_label(len(values)):
                series[0]['label'] = {
                    'show': True, 'position': 'top',
                    'fontSize': 10, 'color': '#1e293b',
                    'formatter': '{c}',
                }

        return {
            'title': _base_title(config.title),
            'tooltip': {
                **_base_tooltip('axis'),
                'axisPointer': {'type': 'cross'},
            },
            'legend': _base_legend() if series_data else None,
            'grid': _base_grid(),
            'xAxis': {
                'type': 'category',
                'data': _format_labels(labels),
                'name': config.x_label if config.x_label != '指标' else '',
                'nameTextStyle': {'color': '#64748b', 'fontSize': 11},
                'axisLabel': {'color': '#64748b', 'fontSize': 11, 'rotate': len(labels) > 6 and 30 or 0},
                'axisLine': {'lineStyle': {'color': '#e2e8f0'}},
                'axisTick': {'show': False},
            },
            'yAxis': {
                'type': 'value',
                'name': config.y_label if config.y_label != '数值' else '',
                'nameTextStyle': {'color': '#64748b', 'fontSize': 11},
                'splitLine': {'lineStyle': {'color': '#f1f5f9', 'type': 'dashed'}},
                'axisLabel': {'color': '#94a3b8', 'fontSize': 10},
                'axisLine': {'show': False},
                'axisTick': {'show': False},
            },
            'series': series,
        }

    # ============ 柱状图 ============

    def _bar_chart(self, config: ChartConfig) -> Dict:
        """柱状图 — 圆角顶部 + 渐变填充 + 数据标签"""
        data = config.data
        labels = data.get("labels", [])
        values = data.get("values", [])
        series_data = data.get("series", {})
        categories = data.get("categories", [])

        # 兼容 labels → categories 转换
        if not categories and not series_data and labels:
            categories = [str(l) for l in labels]

        # 多系列分组柱状图
        if series_data:
            series = []
            for i, (name, vals) in enumerate(series_data.items()):
                color = SERIES_COLORS[i % len(SERIES_COLORS)]
                s = {
                    'name': str(name),
                    'type': 'bar',
                    'data': vals,
                    'barMaxWidth': 40,
                    'itemStyle': {
                        'color': _linear_gradient(color, 'bottom'),
                        'borderRadius': [4, 4, 0, 0],
                    },
                    'emphasis': {
                        'itemStyle': {'color': color},
                    },
                }
                if _should_show_label(len(vals)):
                    s['label'] = {
                        'show': True, 'position': 'top',
                        'fontSize': 10, 'color': '#64748b',
                    }
                series.append(s)
        elif values:
            # 单系列柱状图 — 每个柱子不同颜色
            colors = CHART_COLORS[:len(values)]
            series = [{
                'name': config.title,
                'type': 'bar',
                'data': [
                    {
                        'value': v,
                        'itemStyle': {
                            'color': _linear_gradient(colors[i % len(colors)], 'bottom'),
                            'borderRadius': [4, 4, 0, 0],
                        },
                    }
                    for i, v in enumerate(values)
                ],
                'barMaxWidth': 40,
                'emphasis': {
                    'itemStyle': {'color': CHART_COLORS[0]},
                },
            }]
            if _should_show_label(len(values)):
                series[0]['label'] = {
                    'show': True, 'position': 'top',
                    'fontSize': 10, 'color': '#1e293b',
                }
        else:
            series = []

        x_data = categories if categories else _format_labels(labels)
        return {
            'title': _base_title(config.title),
            'tooltip': _base_tooltip('axis'),
            'legend': _base_legend() if series_data else None,
            'grid': _base_grid(),
            'xAxis': {
                'type': 'category',
                'data': x_data,
                'name': config.x_label if config.x_label != '指标' else '',
                'nameTextStyle': {'color': '#64748b', 'fontSize': 11},
                'axisLabel': {
                    'color': '#64748b', 'fontSize': 11,
                    'rotate': len(x_data) > 6 and 30 or 0,
                },
                'axisLine': {'lineStyle': {'color': '#e2e8f0'}},
                'axisTick': {'show': False},
            },
            'yAxis': {
                'type': 'value',
                'name': config.y_label if config.y_label != '数值' else '',
                'nameTextStyle': {'color': '#64748b', 'fontSize': 11},
                'splitLine': {'lineStyle': {'color': '#f1f5f9', 'type': 'dashed'}},
                'axisLabel': {'color': '#94a3b8', 'fontSize': 10},
                'axisLine': {'show': False},
                'axisTick': {'show': False},
            },
            'series': series,
        }

    # ============ 饼图 ============

    def _pie_chart(self, config: ChartConfig) -> Dict:
        """饼图/环形图 — 扇区圆角 + 阴影 + 标签"""
        data = config.data
        labels = data.get("labels", [])
        values = data.get("values", [])

        # 构建 [{name, value}, ...]
        items = []
        for i, (label, value) in enumerate(zip(labels, values)):
            items.append({
                'name': str(label),
                'value': value,
                'itemStyle': {
                    'color': CHART_COLORS[i % len(CHART_COLORS)],
                    'borderRadius': 6,
                    'borderColor': '#fff',
                    'borderWidth': 2,
                },
            })

        return {
            'title': _base_title(config.title),
            'tooltip': {
                **_base_tooltip('item'),
                'formatter': '{b}: {c} ({d}%)',
            },
            'legend': {
                'orient': 'vertical',
                'right': '5%',
                'top': 'center',
                'textStyle': {'color': '#64748b', 'fontSize': 12},
                'itemWidth': 10,
                'itemHeight': 10,
            },
            'series': [{
                'name': config.title,
                'type': 'pie',
                'radius': ['35%', '65%'],  # 环形图
                'center': ['40%', '55%'],
                'avoidLabelOverlap': False,
                'itemStyle': {
                    'borderRadius': 6,
                    'borderColor': '#fff',
                    'borderWidth': 2,
                },
                'label': {
                    'show': True,
                    'formatter': '{b}\n{d}%',
                    'fontSize': 12,
                    'color': '#334155',
                },
                'emphasis': {
                    'label': {'show': True, 'fontSize': 14, 'fontWeight': 'bold'},
                    'shadowBlur': 20,
                    'shadowColor': 'rgba(0, 0, 0, 0.3)',
                },
                'data': items,
            }],
        }

    # ============ 雷达图 ============

    def _radar_chart(self, config: ChartConfig) -> Dict:
        """雷达图 — 多维财务指标评估（V8.4 美化版，含行业基准对比）"""
        data = config.data
        categories = data.get("categories", [])  # 维度名
        series_data = data.get("series", {})       # {"公司A": [v1,v2,...]}

        # 计算最大值用于设置合理的轴范围
        all_values = []
        for vals in series_data.values():
            all_values.extend(vals)
        max_val = max(all_values) if all_values else 100

        # 动态字号：维度多时缩小
        n_dims = len(categories)
        label_font_size = 10 if n_dims <= 6 else (9 if n_dims <= 8 else 8)
        radius = "65%" if n_dims <= 6 else "70%"

        indicator = [{'name': str(c), 'max': max_val * 1.2} for c in categories]

        # ── V8.4: 行业健康基准线（灰色虚线，用于对比）──
        benchmark = self._financial_benchmark(categories)

        series = []
        # 基准线（灰色虚线，半透明区域）
        if benchmark:
            series.append({
                'name': '行业健康基准',
                'type': 'radar',
                'data': [{
                    'value': benchmark,
                    'name': '行业健康基准',
                    'areaStyle': {'color': 'rgba(100,140,200,0.08)'},
                    'lineStyle': {'color': '#94a3b8', 'width': 1.5, 'type': 'dashed'},
                    'itemStyle': {'color': '#94a3b8'},
                }],
                'symbol': 'diamond',
                'symbolSize': 4,
                'z': 0,
            })

        # 公司数据（实线，鲜艳色）
        for i, (name, vals) in enumerate(series_data.items()):
            color = SERIES_COLORS[i % len(SERIES_COLORS)]
            series.append({
                'name': str(name),
                'type': 'radar',
                'data': [{
                    'value': vals,
                    'name': str(name),
                    'areaStyle': {'color': color + '28', 'opacity': 0.6},
                    'lineStyle': {'color': color, 'width': 2.5},
                    'itemStyle': {'color': color},
                }],
                'symbol': 'circle',
                'symbolSize': 5,
                'z': 1,
            })

        return {
            'title': _base_title(config.title),
            'tooltip': _base_tooltip('item'),
            'legend': _base_legend(),
            'radar': {
                'indicator': indicator,
                'center': ['50%', '55%'],
                'radius': radius,
                'splitNumber': 5,
                'splitArea': {
                    'areaStyle': {'color': ['#f0f4ff', '#fafbff', '#f0f4ff', '#fafbff']},
                },
                'splitLine': {
                    'lineStyle': {'color': '#dce3f0', 'width': 1},
                },
                'axisLine': {
                    'lineStyle': {'color': '#c8d0e0', 'width': 1.5},
                },
                'axisName': {
                    'color': '#4a5568', 'fontSize': label_font_size,
                    'fontWeight': '500', 'overflow': 'truncate',
                    'width': 60,
                },
                'shape': 'circle',
            },
            'series': series,
        }

    @staticmethod
    def _financial_benchmark(categories: list) -> list:
        """根据指标名返回行业健康基准值，无匹配返回 None（该项跳过）"""
        BENCHMARKS = {
            "毛利率": 30, "净利率": 10, "净资产收益率": 15,
            "总资产收益率": 8, "资产负债率": 50, "流动比率": 2.0,
            "速动比率": 1.0, "营收增长率": 15, "净利润增长率": 15,
            "总资产周转率": 0.8, "存货周转率": 5, "经营现金流/净利润比率": 100,
            "自由现金流": 50, "市盈率": 20, "市净率": 3,
        }
        result = []
        for cat in categories:
            val = BENCHMARKS.get(cat)
            if val is None:
                for k, v in BENCHMARKS.items():
                    if k in cat or cat in k:
                        val = v
                        break
            result.append(val)
        # 全部为 None 则不显示基准线
        if all(v is None for v in result):
            return []
        return result

    # ============ 双轴图 ============

    def _dual_axis_chart(self, config: ChartConfig) -> Dict:
        """双轴图 — 柱状图（左轴）+ 折线图（右轴），经典营收+增速组合"""
        data = config.data
        labels = data.get("labels", [])
        bar_values = data.get("bar_values", [])
        line_values = data.get("line_values", [])

        # 防御：数据为空时降级为柱状图
        if not labels or not bar_values:
            logger.warning("dual_axis 数据不完整，降级为柱状图")
            flat_values = {k: v for k, v in data.items()
                          if isinstance(v, (int, float)) and k not in
                          ("labels", "bar_values", "line_values", "bar_label", "line_label")}
            if flat_values:
                config.data["labels"] = list(flat_values.keys())
                config.data["values"] = list(flat_values.values())
                return self._bar_chart(config)
            return self._error_option("数据不完整：缺少 labels 或 bar_values")

        bar_label = data.get("bar_label", "数值")
        line_label = data.get("line_label", "增速")

        bar_color = CHART_COLORS[0]  # Indigo
        line_color = CHART_COLORS[3]  # Red

        return {
            'title': _base_title(config.title),
            'tooltip': _base_tooltip('axis'),
            'legend': _base_legend(),
            'grid': _base_grid(),
            'xAxis': {
                'type': 'category',
                'data': _format_labels(labels),
                'axisLabel': {
                    'color': '#64748b', 'fontSize': 11,
                    'rotate': len(labels) > 6 and 30 or 0,
                },
                'axisLine': {'lineStyle': {'color': '#e2e8f0'}},
                'axisTick': {'show': False},
            },
            'yAxis': [
                {
                    'type': 'value',
                    'name': bar_label,
                    'nameTextStyle': {'color': bar_color, 'fontSize': 11},
                    'splitLine': {'lineStyle': {'color': '#f1f5f9', 'type': 'dashed'}},
                    'axisLabel': {'color': bar_color, 'fontSize': 10},
                    'axisLine': {'show': False},
                    'axisTick': {'show': False},
                },
                {
                    'type': 'value',
                    'name': line_label + ' (%)',
                    'nameTextStyle': {'color': line_color, 'fontSize': 11},
                    'splitLine': {'show': False},
                    'axisLabel': {
                        'color': line_color, 'fontSize': 10,
                        'formatter': '{value}%',
                    },
                    'axisLine': {'show': False},
                    'axisTick': {'show': False},
                },
            ],
            'series': [
                {
                    'name': bar_label,
                    'type': 'bar',
                    'data': bar_values,
                    'barMaxWidth': 40,
                    'itemStyle': {
                        'color': _linear_gradient(bar_color, 'bottom'),
                        'borderRadius': [4, 4, 0, 0],
                    },
                    'emphasis': {'itemStyle': {'color': bar_color}},
                },
                {
                    'name': line_label,
                    'type': 'line',
                    'yAxisIndex': 1,
                    'data': line_values if line_values and len(line_values) == len(labels) else [],
                    'smooth': True,
                    'symbol': 'diamond',
                    'symbolSize': 8,
                    'lineStyle': {'width': 2.5, 'color': line_color},
                    'itemStyle': {'color': line_color},
                },
            ] if line_values and len(line_values) == len(labels) else [
                {
                    'name': bar_label,
                    'type': 'bar',
                    'data': bar_values,
                    'barMaxWidth': 40,
                    'itemStyle': {
                        'color': _linear_gradient(bar_color, 'bottom'),
                        'borderRadius': [4, 4, 0, 0],
                    },
                },
            ],
        }

    # ============ 错误降级 ============

    def _error_option(self, error_msg: str) -> Dict:
        """生成错误提示图表"""
        return {
            'title': {
                'text': '图表生成失败',
                'subtext': error_msg,
                'left': 'center',
                'top': 'center',
                'textStyle': {'color': '#ef4444', 'fontSize': 16},
                'subtextStyle': {'color': '#94a3b8', 'fontSize': 12},
            },
        }
