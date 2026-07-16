import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { useAnalysisStore } from '@/stores/analysis';
import { useDocumentStore } from '@/stores/document';

/**
 * V8.2 E2E 流程测试 — 跨页面用户旅程
 *
 * 与现有单元测试互补: 测跨页面状态保持和完整用户旅程
 * 已有单元测试覆盖: 按钮禁用、模板加载、RAG问答、报告渲染
 */

describe('E2E: 分析→返回→报告页结果保持', () => {
  beforeEach(() => {
    useAnalysisStore.getState().reset();
  });

  it('完成分析 → 返回 → 侧边栏到报告页 → store中结果仍渲染', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 分析
    await user.click(await screen.findByText('贵州茅台'));
    await user.click(screen.getByText('盈利能力评估'));
    await user.click(screen.getByRole('button', { name: /开始分析/ }));

    // 等待报告
    await waitFor(() => {
      expect(screen.getByText(/分析报告/)).toBeInTheDocument();
    }, { timeout: 10000 });

    // 返回 → 开始分析按钮重现
    await user.click(screen.getByText(/返回重新分析/));
    expect(screen.getByRole('button', { name: /开始分析/ })).toBeInTheDocument();

    // 侧边栏 → 报告页 → 结果仍可见（跨页面状态保持）
    const sidebarLink = screen.getAllByRole('link', { name: /报告展示/ })[0];
    await user.click(sidebarLink);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '分析报告' })).toBeInTheDocument();
    });
  });
});

describe('E2E: 三页面直接访问', () => {
  it('报告页无结果 → 空状态', async () => {
    useAnalysisStore.getState().reset();
    render(
      <MemoryRouter initialEntries={['/report']}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '暂无分析结果' })).toBeInTheDocument();
    });
  });

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

  it('预设分析页 → 公司标签和模板', async () => {
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

describe('E2E: RAG问答（复用已有测试模式）', () => {
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

    // 等文档列表 + 选文档（复用已有测试的已验证模式）
    await screen.findByText('贵州茅台2024年报.pdf');
    await user.click(screen.getByText('贵州茅台2024年报.pdf'));

    // 输入问题（用 placeholder 匹配，与已有测试一致）
    const input = screen.getByPlaceholderText(/输入问题/);
    await user.type(input, '茅台2024年营收增长了多少？');

    // 发送
    await user.click(screen.getByRole('button', { name: /发送/ }));

    // 等待回答
    await waitFor(() => {
      const matches = screen.getAllByText(/营业收入/);
      expect(matches.length).toBeGreaterThanOrEqual(2);
    });

    // 来源引用
    expect(screen.getByText('📎 来源引用')).toBeInTheDocument();
  });
});
