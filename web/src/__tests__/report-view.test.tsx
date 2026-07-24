import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { useAnalysisStore } from '@/stores/analysis';

/**
 * V8.3: 分析结果展示 + 导出功能测试
 * 原独立的 /report 页面已合并到分析工作台，导出按钮直接放在结果区。
 */

describe('分析结果展示', () => {
  beforeEach(() => {
    useAnalysisStore.getState().reset();
  });

  it('分析完成后结果区包含导出按钮', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 执行分析
    await user.click(await screen.findByText('贵州茅台'));
    await user.click(screen.getByText('盈利能力评估'));
    await user.click(screen.getByRole('button', { name: /开始/ }));

    // 等待分析完成
    await waitFor(() => {
      expect(screen.getByText(/分析报告/)).toBeInTheDocument();
    }, { timeout: 10000 });

    // 验证导出按钮存在
    expect(screen.getByText(/导出PDF/)).toBeInTheDocument();
    expect(screen.getByText(/导出MD/)).toBeInTheDocument();

    // 验证返回按钮存在
    expect(screen.getByText(/返回/)).toBeInTheDocument();
  });

  it('返回后结果消失，可重新分析', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 分析
    await user.click(await screen.findByText('贵州茅台'));
    await user.click(screen.getByText('盈利能力评估'));
    await user.click(screen.getByRole('button', { name: /开始/ }));

    await waitFor(() => {
      expect(screen.getByText(/分析报告/)).toBeInTheDocument();
    });

    // 返回
    await user.click(screen.getByText(/返回/));

    // 按钮重新出现
    expect(screen.getByRole('button', { name: /开始/ })).toBeInTheDocument();
  });
});
