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
# 参考 Indigo 主色调，兼顾问色彩和色盲友好
CHART_COLORS = [
    '#4f46e5',  # Indigo 靛蓝 — 主色
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

# 系列级配色（用于折线/柱状图中同一图表的多条数据线）
SERIES_COLORS = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
                 '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1']


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

    def run(self, chart_type: str = "bar", title: str = "财务分析图表",
            data: dict = None, x_label: str = "", y_label: str = "",
            **kwargs) -> Dict[str, Any]:
        """
        生成 ECharts option 并返回。

        参数（与 Planner 输出的 params 字段对应）:
            chart_type: line/bar/pie/radar/dual_axis
            title: 图表标题
            data: 图表数据 {"labels": [...], "values": [...]}
            x_label: X 轴标签
            y_label: Y 轴标签

        返回:
            {"chart_option": <ECharts option dict>}
        """
        if data is None:
            data = {}

        # 合并 kwargs 中的数值参数到 data（兼容 LLM 产出 var=value 格式）
        numeric_extra = {k: v for k, v in {**kwargs, **data}.items()
                        if isinstance(v, (int, float))}
        if numeric_extra and not data.get("values") and not data.get("labels"):
            data["labels"] = list(numeric_extra.keys())
            data["values"] = list(numeric_extra.values())

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
            return {"chart_option": option}
        except Exception as e:
            logger.error(f"图表生成失败 [{config.chart_type}]: {e}")
            return {"chart_option": self._error_option(str(e))}

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
        """雷达图 — 多维财务指标评估"""
        data = config.data
        categories = data.get("categories", [])  # 维度名
        series_data = data.get("series", {})       # {"公司A": [v1,v2,...]}

        # 计算最大值用于设置合理的轴范围
        all_values = []
        for vals in series_data.values():
            all_values.extend(vals)
        max_val = max(all_values) if all_values else 100

        indicator = [{'name': str(c), 'max': max_val * 1.2} for c in categories]

        series = []
        for i, (name, vals) in enumerate(series_data.items()):
            color = SERIES_COLORS[i % len(SERIES_COLORS)]
            series.append({
                'name': str(name),
                'type': 'radar',
                'data': [{
                    'value': vals,
                    'name': str(name),
                    'areaStyle': {'color': color + '33'},
                    'lineStyle': {'color': color, 'width': 2},
                    'itemStyle': {'color': color},
                }],
                'symbol': 'circle',
                'symbolSize': 6,
            })

        return {
            'title': _base_title(config.title),
            'tooltip': _base_tooltip('item'),
            'legend': _base_legend(),
            'radar': {
                'indicator': indicator,
                'center': ['50%', '55%'],
                'radius': '60%',
                'splitArea': {
                    'areaStyle': {'color': ['#f8fafc', '#ffffff']},
                },
                'axisName': {'color': '#64748b', 'fontSize': 11},
            },
            'series': series,
        }

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
