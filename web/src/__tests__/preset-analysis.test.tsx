import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { useAnalysisStore } from '@/stores/analysis';

describe('预设分析页面', () => {
  beforeEach(() => {
    // 重置分析状态，避免跨测试污染
    useAnalysisStore.getState().reset();
  });

  it('渲染5个预设公司标签', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('贵州茅台')).toBeInTheDocument();
      expect(screen.getByText('比亚迪')).toBeInTheDocument();
      expect(screen.getByText('宁德时代')).toBeInTheDocument();
      expect(screen.getByText('五粮液')).toBeInTheDocument();
      expect(screen.getByText('招商银行')).toBeInTheDocument();
    });
  });

  it('加载并显示分析模板卡片', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('盈利能力评估')).toBeInTheDocument();
      expect(screen.getByText('杜邦分析')).toBeInTheDocument();
      expect(screen.getByText('成长性分析')).toBeInTheDocument();
    });
  });

  it('选择公司后点击分析模板 → 调用 API 并展示结果', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 1. 点击公司标签
    await user.click(await screen.findByText('贵州茅台'));

    // 2. 点击模板卡片"盈利能力评估"
    await user.click(screen.getByText('盈利能力评估'));

    // 3. 点击分析按钮
    await user.click(screen.getByRole('button', { name: /开始/ }));

    // 4. 等待结果展示
    await waitFor(() => {
      expect(screen.getByText(/分析报告/)).toBeInTheDocument();
    });
  });

  it('选择公司和模板后 → 显示推荐问题，点击可填入输入框', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 点击公司
    await user.click(await screen.findByText('贵州茅台'));
    // 点击模板
    await user.click(screen.getByText('盈利能力评估'));

    // 推荐问题出现
    await waitFor(() => {
      expect(screen.getByText(/推荐问题/)).toBeInTheDocument();
    });

    // 点击推荐问题按钮（第二个含"毛利率"的按钮，第一个是模板卡片描述）
    const qBtns = screen.getAllByRole('button', { name: /毛利率/ });
    expect(qBtns.length).toBeGreaterThanOrEqual(2);
    await user.click(qBtns[1]);

    // 输入框被填入问题文本
    const input = screen.getByRole('textbox', { name: /自定义分析问题/ }) as HTMLInputElement;
    expect(input.value).toContain('毛利率');
  });

  it('未选公司时分析按钮禁用', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 等待模板加载完毕
    await screen.findByText('盈利能力评估');

    // 分析按钮应该被禁用（没选公司）
    const btn = screen.getByRole('button', { name: /请先选择/ });
    expect(btn).toBeDisabled();
  });
});
