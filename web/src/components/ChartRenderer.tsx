import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';

/**
 * ECharts 图表渲染组件 — V9.0 专业版
 *
 * 专业财务特性（后端注入的 ECharts option）:
 * - toolbox: 保存图片 + 数据视图
 * - dataZoom: 时间序列底部缩放滑块
 * - 十字准线 + 精确 tooltip
 * - 图例点击切换
 *
 * 前端增强:
 * - ResizeObserver 自适应容器
 * - 动态高度: 柱图360/雷达图500/饼图400
 * - 加载骨架屏 + 错误兜底
 *
 * V9.1 修复: echarts 画布挂载到独立子 div, 避免 React removeChild 崩溃白屏。
 * 根因: 旧实现 echarts.init 直接在 React 管理的容器内插 canvas, 与 React DOM
 * reconciliation 冲突 — 移除骨架屏/错误层时 removeChild 报
 * "The node to be removed is not a child of this node", 整个 React 树崩溃。
 */
export default function ChartRenderer({
  option,
  className = '',
  height: propHeight,
}: {
  option: Record<string, unknown> | null;
  className?: string;
  height?: number;
}) {
  const chartMountRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  // 动态高度: 雷达图需要更多空间
  const dynamicHeight = (() => {
    if (propHeight) return propHeight;
    if (!option) return 360;
    // 雷达图: 500px (多维度需要大图)
    const series = option.series;
    if (Array.isArray(series) && series[0] && typeof series[0] === 'object' && (series[0] as Record<string,unknown>).type === 'radar') {
      return 500;
    }
    // 饼图: 400px
    if (Array.isArray(series) && series[0] && typeof series[0] === 'object' && (series[0] as Record<string,unknown>).type === 'pie') {
      return 400;
    }
    // 默认: 360px
    return 360;
  })();

  useEffect(() => {
    if (!option) {
      setReady(false);
      setError(null);
      return;
    }

    const mountEl = chartMountRef.current;
    if (!mountEl) return;

    // 销毁旧实例
    if (chartRef.current) {
      chartRef.current.dispose();
      chartRef.current = null;
    }

    try {
      const chart = echarts.init(mountEl, null, { renderer: 'canvas' });

      // 触屏设备增大 toolbox 图标
      const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

      // 注入前端侧 valueFormatter（JSON 无法序列化函数，后端只负责静态配置）
      const tooltipConfig = (option.tooltip || {}) as Record<string, unknown>;
      const finalOption = {
        ...(option as Record<string, unknown>),
        toolbox: {
          ...(option.toolbox as Record<string, unknown> || {}),
          iconStyle: isTouchDevice ? { borderWidth: 2 } : {},
        },
        tooltip: {
          ...tooltipConfig,
          valueFormatter: (value: unknown) =>
            typeof value === 'number'
              ? value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
              : String(value ?? ''),
        },
      };

      chart.setOption(finalOption, true);

      chartRef.current = chart;
      setReady(true);
      setError(null);

      const ro = new ResizeObserver(() => chart.resize());
      ro.observe(mountEl);

      return () => {
        ro.disconnect();
        chart.dispose();
        chartRef.current = null;
      };
    } catch (e) {
      setReady(false);
      setError(e instanceof Error ? e.message : '图表渲染失败');
      return undefined;
    }
  }, [option]);

  return (
    <div className={`w-full relative ${className}`} style={{ height: dynamicHeight }}>
      {/* ECharts 画布挂载点 — 独立子 div，React 不管理其内部（避免 removeChild 崩溃） */}
      <div ref={chartMountRef} className="absolute inset-0" />

      {/* 错误状态 */}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center border border-red-200 rounded-xl bg-red-50/50">
          <div className="text-center px-4">
            <div className="text-red-500 text-sm font-medium mb-1">图表渲染失败</div>
            <div className="text-red-400 text-xs">{error}</div>
          </div>
        </div>
      )}

      {/* 加载骨架屏 */}
      {!ready && !error && (
        <div className="absolute inset-0 flex items-center justify-center border border-slate-200 rounded-xl bg-gradient-to-b from-slate-50 to-white">
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 border-2 border-indigo-300 border-t-transparent rounded-full animate-spin" />
            <div className="text-slate-400 text-xs font-medium">图表加载中...</div>
          </div>
        </div>
      )}
    </div>
  );
}
