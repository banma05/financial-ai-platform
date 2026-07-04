"""
图表生成工具 — matplotlib 生成财务图表

支持 5 种图表类型：
- line: 折线图（趋势分析）
- bar: 柱状图（对比分析）
- pie: 饼图（结构分析）
- radar: 雷达图（多维度评估）
- dual_axis: 双轴图（营收+增速对比）

图表以 base64 编码 PNG 返回，前端直接 st.image() 展示。
"""
import io
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
from loguru import logger

import matplotlib
matplotlib.use("Agg")  # 非交互后端，适合服务端
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib import rcParams

from agent.schemas import ChartConfig
from config import CHART_OUTPUT_DIR


# ==================== 中文字体配置 ====================

def _setup_chinese_font():
    """配置 matplotlib 中文字体"""
    # 尝试常见中文字体
    chinese_fonts = [
        "Microsoft YaHei",      # Windows 雅黑
        "SimHei",                # Windows 黑体
        "SimSun",                # Windows 宋体
        "WenQuanYi Micro Hei",   # Linux
        "WenQuanYi Zen Hei",     # Linux
        "Noto Sans CJK SC",      # Linux/通用
        "PingFang SC",           # macOS
        "Heiti SC",              # macOS
    ]

    available_fonts = {f.name for f in fm.fontManager.ttflist}

    for font in chinese_fonts:
        if font in available_fonts:
            rcParams["font.sans-serif"] = [font, "DejaVu Sans"]
            rcParams["axes.unicode_minus"] = False  # 解决负号显示问题
            logger.info(f"使用中文字体: {font}")
            return font

    # 没找到中文字体，降级处理
    logger.warning("未找到中文字体，图表中文可能显示为方框")
    rcParams["font.sans-serif"] = ["DejaVu Sans"]
    rcParams["axes.unicode_minus"] = False
    return "DejaVu Sans"


# 模块加载时执行一次
_CHINESE_FONT_NAME = _setup_chinese_font()


def _fig_to_base64(fig) -> str:
    """将 matplotlib Figure 转为 base64 编码的 PNG 字符串"""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return img_base64


# ==================== 图表生成类 ====================

class ChartTool:
    """
    财务图表生成工具。

    用法:
        tool = ChartTool()
        base64_img = tool.run(ChartConfig(
            chart_type="line",
            title="茅台近三年毛利率趋势",
            data={"labels": ["2022","2023","2024"], "values": [92.0, 91.8, 91.5]},
        ))
    """

    def __init__(self, output_dir: str = None):
        self.name = "chart"
        self.output_dir = output_dir or str(CHART_OUTPUT_DIR)

    def run(self, chart_type: str = "bar", title: str = "财务分析图表",
            data: dict = None, x_label: str = "", y_label: str = "",
            **kwargs) -> str:
        """
        生成图表并返回 base64 编码的 PNG。

        参数（与 Planner 输出的 params 字段对应）:
            chart_type: line/bar/pie/radar/dual_axis
            title: 图表标题
            data: 图表数据 {"labels": [...], "values": [...]}
            x_label: X 轴标签
            y_label: Y 轴标签

        返回:
            base64 编码的 PNG 字符串
        """
        # 从依赖注入的数据中提取 labels/values
        if data is None:
            data = {}
        # 合并 kwargs 中的数值参数到 data
        numeric_data = {k: v for k, v in {**kwargs, **data}.items() if isinstance(v, (int, float))}
        if numeric_data and not data.get("values"):
            data["labels"] = list(numeric_data.keys())
            data["values"] = list(numeric_data.values())

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
            return method(config)
        except Exception as e:
            logger.error(f"图表生成失败 [{config.chart_type}]: {e}")
            return _fig_to_base64(self._error_chart(str(e)))

    def _line_chart(self, config: ChartConfig) -> str:
        """折线图：适用于趋势分析"""
        data = config.data
        labels = data.get("labels", [])
        values = data.get("values", [])

        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(labels, values, marker="o", linewidth=2, markersize=6, color="#2E86AB")
        ax.set_title(config.title, fontsize=14, fontweight="bold")
        ax.set_xlabel(config.x_label or "年份")
        ax.set_ylabel(config.y_label or "数值")
        ax.grid(True, alpha=0.3)

        # 在数据点上标注数值
        for i, v in enumerate(values):
            ax.annotate(str(v), (labels[i], v), textcoords="offset points",
                       xytext=(0, 10), ha="center", fontsize=9)

        return _fig_to_base64(fig)

    def _bar_chart(self, config: ChartConfig) -> str:
        """柱状图：适用于对比分析（分组柱状图）"""
        data = config.data
        categories = data.get("categories", [])  # X 轴类别
        series = data.get("series", {})           # {"系列名": [值列表], ...}

        fig, ax = plt.subplots(figsize=(8, 4.5))
        colors = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#6A994E"]

        x = range(len(categories))
        bar_width = 0.8 / max(len(series), 1)

        for i, (name, values) in enumerate(series.items()):
            offset = (i - (len(series) - 1) / 2) * bar_width
            positions = [pos + offset for pos in x]
            ax.bar(positions, values, bar_width, label=name, color=colors[i % len(colors)])

        ax.set_title(config.title, fontsize=14, fontweight="bold")
        ax.set_xlabel(config.x_label or "类别")
        ax.set_ylabel(config.y_label or "数值")
        ax.set_xticks(x)
        ax.set_xticklabels(categories)
        ax.legend()
        ax.grid(True, alpha=0.3, axis="y")

        return _fig_to_base64(fig)

    def _pie_chart(self, config: ChartConfig) -> str:
        """饼图：适用于结构分析"""
        data = config.data
        labels = data.get("labels", [])
        values = data.get("values", [])

        fig, ax = plt.subplots(figsize=(7, 7))
        colors = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#6A994E", "#3B1F2B"]

        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct="%1.1f%%",
            colors=colors[:len(labels)], startangle=90,
            textprops={"fontsize": 10}
        )
        ax.set_title(config.title, fontsize=14, fontweight="bold")

        return _fig_to_base64(fig)

    def _radar_chart(self, config: ChartConfig) -> str:
        """雷达图：适用于多维度综合评估"""
        import numpy as np

        data = config.data
        categories = data.get("categories", [])  # 维度名称
        values = data.get("series", {})            # {"公司A": [v1, v2, ...], ...}

        N = len(categories)
        angles = [n / float(N) * 2 * np.pi for n in range(N)]
        angles += angles[:1]  # 闭合

        fig, ax = plt.subplots(figsize=(7, 7), subplot_kw=dict(polar=True))
        colors = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D"]

        for i, (name, vals) in enumerate(values.items()):
            vals_plot = list(vals) + [vals[0]]
            ax.plot(angles, vals_plot, "o-", linewidth=2, label=name, color=colors[i % len(colors)])
            ax.fill(angles, vals_plot, alpha=0.1, color=colors[i % len(colors)])

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=10)
        ax.set_title(config.title, fontsize=14, fontweight="bold", pad=20)
        ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

        return _fig_to_base64(fig)

    def _dual_axis_chart(self, config: ChartConfig) -> str:
        """双轴图：柱状图（左轴）+ 折线图（右轴），适用于营收+增速等场景"""
        data = config.data
        labels = data.get("labels", [])
        bar_values = data.get("bar_values", [])     # 左轴（绝对值）
        line_values = data.get("line_values", [])   # 右轴（百分比）
        bar_label = data.get("bar_label", "数值")
        line_label = data.get("line_label", "增速")

        fig, ax1 = plt.subplots(figsize=(8, 4.5))

        # 左轴：柱状图
        ax1.bar(labels, bar_values, color="#2E86AB", alpha=0.7, label=bar_label)
        ax1.set_xlabel(config.x_label or "年份")
        ax1.set_ylabel(bar_label, color="#2E86AB")
        ax1.tick_params(axis="y", labelcolor="#2E86AB")

        # 在柱子上标注数值
        for i, v in enumerate(bar_values):
            ax1.text(i, v, str(v), ha="center", va="bottom", fontsize=9)

        # 右轴：折线图
        ax2 = ax1.twinx()
        ax2.plot(labels, line_values, marker="s", linewidth=2, color="#A23B72", label=line_label)
        ax2.set_ylabel(line_label + " (%)", color="#A23B72")
        ax2.tick_params(axis="y", labelcolor="#A23B72")

        ax1.set_title(config.title, fontsize=14, fontweight="bold")

        # 合并图例
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

        return _fig_to_base64(fig)

    def _error_chart(self, error_msg: str) -> plt.Figure:
        """错误时的降级图表"""
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, f"图表生成失败\n{error_msg}",
                ha="center", va="center", fontsize=12, color="red",
                transform=ax.transAxes)
        ax.axis("off")
        return fig
