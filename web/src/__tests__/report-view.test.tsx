import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { useAnalysisStore } from '@/stores/analysis';

describe('报告展示页面', () => {
  beforeEach(() => {
    useAnalysisStore.getState().reset();
  });

  it('无分析结果时显示提示信息', async () => {
    render(
      <MemoryRouter initialEntries={['/report']}>
        <App />
      </MemoryRouter>,
    );

    // 提示用户先进行分析
    await waitFor(() => {
      expect(screen.getByText(/暂无分析结果/)).toBeInTheDocument();
    });
  });

  it('有分析结果时渲染 Markdown 报告内容', async () => {
    // 预先设置分析结果
    useAnalysisStore.getState().setResult({
      report: '## 盈利能力分析报告\n\n贵州茅台 **2024年** 营收同比增长 **15%**。\n\n### 关键指标\n\n- 毛利率: 91.96%\n- 净利率: 52.08%\n- ROE: 32.17%',
      charts: [],
      processing_time: 3.2,
      task_count: 8,
      clarification: null,
    });

    render(
      <MemoryRouter initialEntries={['/report']}>
        <App />
      </MemoryRouter>,
    );

    // Markdown 渲染为 HTML 标题
    await waitFor(() => {
      expect(screen.getByText('盈利能力分析报告')).toBeInTheDocument();
      expect(screen.getByText('关键指标')).toBeInTheDocument();
    });

    // 粗体文本
    expect(screen.getByText('15%')).toBeInTheDocument();

    // 元信息
    expect(screen.getByText(/3.2 秒/)).toBeInTheDocument();
    expect(screen.getByText(/8 /)).toBeInTheDocument();
  });

  it('从预设分析页完成分析后，切换到报告页可看到结果', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 在预设分析页完成一次分析
    await user.click(await screen.findByText('贵州茅台'));
    await user.click(screen.getByText('盈利能力评估'));
    await user.click(screen.getByRole('button', { name: /开始分析/ }));
    await waitFor(() => {
      expect(screen.getByText(/分析报告/)).toBeInTheDocument();
    });

    // 点击返回，再导航到报告页
    await user.click(screen.getByText('← 返回重新分析'));

    // 通过侧边栏切换到报告页
    await user.click(screen.getByRole('link', { name: /报告展示/ }));

    // 报告页显示之前的分析结果（h1 为"分析报告"）
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: '分析报告' })).toBeInTheDocument();
    });
  });
});
