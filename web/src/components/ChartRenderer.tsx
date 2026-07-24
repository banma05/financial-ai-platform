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
  const containerRef = useRef<HTMLDivElement>(null);
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
    if (!containerRef.current) return;

    if (!option) {
      setReady(false);
      setError(null);
      return;
    }

    // 销毁旧实例
    if (chartRef.current) {
      chartRef.current.dispose();
      chartRef.current = null;
    }

    try {
      const chart = echarts.init(containerRef.current, null, { renderer: 'canvas' });

      // 触屏设备增大 toolbox 图标
      const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

      chart.setOption(
        {
          ...(option as Record<string, unknown>),
          toolbox: {
            ...(option.toolbox as Record<string, unknown> || {}),
            iconStyle: isTouchDevice ? { borderWidth: 2 } : {},
          },
        },
        true,
      );

      chartRef.current = chart;
      setReady(true);
      setError(null);

      const ro = new ResizeObserver(() => chart.resize());
      ro.observe(containerRef.current);

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

  // 错误状态
  if (error) {
    return (
      <div
        className={`w-full flex items-center justify-center border border-red-200 rounded-xl bg-red-50/50 ${className}`}
        style={{ height: dynamicHeight }}
      >
        <div className="text-center px-4">
          <div className="text-red-500 text-sm font-medium mb-1">图表渲染失败</div>
          <div className="text-red-400 text-xs">{error}</div>
        </div>
      </div>
    );
  }

  // 加载骨架屏
  if (!ready) {
    return (
      <div
        className={`w-full flex items-center justify-center border border-slate-200 rounded-xl bg-gradient-to-b from-slate-50 to-white ${className}`}
        style={{ height: dynamicHeight }}
      >
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-2 border-indigo-300 border-t-transparent rounded-full animate-spin" />
          <div className="text-slate-400 text-xs font-medium">图表加载中...</div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`w-full ${className}`}
      style={{ height: dynamicHeight }}
    />
  );
}
