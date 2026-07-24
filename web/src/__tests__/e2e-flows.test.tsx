import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { useAnalysisStore } from '@/stores/analysis';
import { useDocumentStore } from '@/stores/document';

/**
 * V8.3 E2E 流程测试 — 跨页面用户旅程
 *
 * V8.3 架构变更: 砍掉独立 /report 页面，分析+结果+导出统一在分析工作台。
 */

describe('E2E: 分析→返回→再来一次', () => {
  beforeEach(() => {
    useAnalysisStore.getState().reset();
  });

  it('完成分析 → 返回 → 重新选择 → 按钮可用', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 选择公司和模板
    await user.click(await screen.findByText('贵州茅台'));
    await user.click(screen.getByText('盈利能力评估'));
    await user.click(screen.getByRole('button', { name: /开始/ }));

    // 等待报告出现
    await waitFor(() => {
      expect(screen.getByText(/分析报告/)).toBeInTheDocument();
    }, { timeout: 10000 });

    // 返回 → 按钮重现
    await user.click(screen.getByText(/返回/));
    expect(screen.getByRole('button', { name: /开始/ })).toBeInTheDocument();

    // 可以换公司再分析
    await user.click(screen.getByText('比亚迪'));
    expect(screen.getByRole('button', { name: /开始/ })).toBeInTheDocument();
  });
});

describe('E2E: 页面直接访问', () => {
  it('文档上传页 → 文档列表', async () => {
    render(
      <MemoryRouter initialEntries={['/upload']}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText(/贵州茅台2024年报/)).toBeInTheDocument();
    });
  });

  it('分析工作台 → 公司标签和模板', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByText('贵州茅台')).toBeInTheDocument();
      expect(screen.getByText('盈利能力评估')).toBeInTheDocument();
    });
  });
});

describe('E2E: RAG问答', () => {
  beforeEach(() => {
    useDocumentStore.getState().clearChat();
    useDocumentStore.setState({ documents: [], uploadError: null, chatError: null });
  });

  it('选文档 → 输入问题 → 发送 → 回答+来源', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/upload']}>
        <App />
      </MemoryRouter>,
    );

    await screen.findByText('贵州茅台2024年报.pdf');
    await user.click(screen.getByText('贵州茅台2024年报.pdf'));

    const input = screen.getByPlaceholderText(/输入问题/);
    await user.type(input, '茅台2024年营收增长了多少？');

    await user.click(screen.getByRole('button', { name: /发送/ }));

    await waitFor(() => {
      const matches = screen.getAllByText(/营业收入/);
      expect(matches.length).toBeGreaterThanOrEqual(2);
    });

    expect(screen.getByText('📎 来源引用')).toBeInTheDocument();
  });
});
