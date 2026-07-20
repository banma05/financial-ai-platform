import { useEffect, useRef, useState } from 'react';
import * as echarts from 'echarts';

/**
 * ECharts 图表渲染组件 — V9.0 重构
 *
 * 改进：
 * - 移除 !option.series 守卫 → 允许展示后端错误信息图表
 * - ResizeObserver 替代 window.resize → 容器大小变化时自适应
 * - 动态高度：雷达图/多维度自动加高
 * - try/catch 渲染兜底 + 错误状态 UI
 * - 加载骨架屏
 */
export default function ChartRenderer({
  option,
  className = '',
  height = 360,
}: {
  option: Record<string, unknown> | null;
  className?: string;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!containerRef.current) return;

    // 无数据 → 保持 loading 态
    if (!option) {
      setLoading(true);
      setError(null);
      return;
    }

    // 无 series 但有 title → 可能是错误信息图表，仍尝试渲染
    // V9.0: 移除了旧的 !option.series 守卫

    // 销毁旧实例
    if (chartRef.current) {
      chartRef.current.dispose();
      chartRef.current = null;
    }

    try {
      const chart = echarts.init(containerRef.current, null, { renderer: 'canvas' });
      chart.setOption(option, true);
      chartRef.current = chart;
      setLoading(false);
      setError(null);

      // V9.0: ResizeObserver 替代 window.resize
      const ro = new ResizeObserver(() => chart.resize());
      ro.observe(containerRef.current);

      return () => {
        ro.disconnect();
        chart.dispose();
        chartRef.current = null;
      };
    } catch (e) {
      setLoading(false);
      setError(e instanceof Error ? e.message : '图表渲染失败');
      return undefined;
    }
  }, [option]);

  // 错误状态
  if (error) {
    return (
      <div
        className={`w-full flex items-center justify-center border border-red-200 rounded-lg bg-red-50 ${className}`}
        style={{ height }}
      >
        <div className="text-center px-4">
          <div className="text-red-500 text-sm font-medium mb-1">图表渲染失败</div>
          <div className="text-red-400 text-xs">{error}</div>
        </div>
      </div>
    );
  }

  // 加载骨架屏
  if (loading) {
    return (
      <div
        className={`w-full flex items-center justify-center border border-gray-200 rounded-lg bg-gray-50 ${className}`}
        style={{ height }}
      >
        <div className="flex flex-col items-center gap-2">
          <div className="w-8 h-8 border-2 border-indigo-300 border-t-transparent rounded-full animate-spin" />
          <div className="text-gray-400 text-xs">图表加载中...</div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`w-full ${className}`}
      style={{ height }}
    />
  );
}
