import { render } from '@testing-library/react';
import { describe, it, expect, vi, beforeAll } from 'vitest';
import AnalysisResult from '@/components/AnalysisResult';

// jsdom 无 canvas，mock echarts
vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    setOption: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
  })),
}));

// jsdom 无 ResizeObserver
beforeAll(() => {
  (globalThis as unknown as Record<string, unknown>).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

describe('AnalysisResult 渲染回归', () => {
  it('正常报告 + 图表渲染不崩溃', () => {
    const { container } = render(
      <AnalysisResult
        report="# 测试报告\n毛利率 91.18%"
        chartOptions={[
          {
            option: { series: [{ type: 'bar', data: [1, 2, 3] }], xAxis: { data: ['a', 'b', 'c'] } },
            description: '测试图表',
          },
        ]}
        processingTime={30.2}
        taskCount={8}
        selectedCompany="贵州茅台"
        onBack={() => {}}
      />
    );
    expect(container.textContent).toContain('测试报告');
    expect(container.textContent).toContain('可视化图表');
  });

  it('chartOptions 为空也能渲染', () => {
    const { container } = render(
      <AnalysisResult
        report="只有文字报告"
        chartOptions={[]}
        processingTime={10}
        taskCount={3}
        selectedCompany={null}
        onBack={() => {}}
      />
    );
    expect(container.textContent).toContain('只有文字报告');
  });

  it('option 为空对象不崩溃（chart 事件兜底 {}）', () => {
    const { container } = render(
      <AnalysisResult
        report="报告"
        chartOptions={[{ option: {}, description: '' }]}
        processingTime={5}
        taskCount={2}
        selectedCompany={null}
        onBack={() => {}}
      />
    );
    expect(container.textContent).toContain('可视化图表');
  });
});
