import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';

/**
 * ECharts 图表渲染组件
 *
 * 接收后端生成的 ECharts option JSON，自动初始化 + 自适应容器大小。
 * V8.3: 替代旧的 <img> 标签静态图片渲染。
 */
export default function ChartRenderer({
  option,
  className = '',
}: {
  option: Record<string, unknown>;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!containerRef.current || !option || !option.series) return;

    // 如果已有实例则先销毁（option 变化时重新渲染）
    if (chartRef.current) {
      chartRef.current.dispose();
    }

    // 创建 ECharts 实例
    const chart = echarts.init(containerRef.current, null, {
      renderer: 'canvas',
    });

    // 应用配置（notMerge=true 确保完全替换）
    chart.setOption(option, true);
    chartRef.current = chart;

    // 响应式 resize
    const handleResize = () => chart.resize();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, [option]);

  return (
    <div
      ref={containerRef}
      className={`w-full ${className}`}
      style={{ height: 360 }}
    />
  );
}
