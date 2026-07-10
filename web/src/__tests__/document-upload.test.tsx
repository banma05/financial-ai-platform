import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { useDocumentStore } from '@/stores/document';

describe('文档上传页面', () => {
  beforeEach(() => {
    useDocumentStore.getState().clearChat();
    useDocumentStore.setState({ documents: [], uploadError: null, chatError: null });
  });

  it('显示拖拽上传区域', async () => {
    render(
      <MemoryRouter initialEntries={['/upload']}>
        <App />
      </MemoryRouter>,
    );

    // 上传区域的提示文字
    expect(screen.getByText(/拖拽/)).toBeInTheDocument();
  });

  it('加载并显示已上传文档列表', async () => {
    render(
      <MemoryRouter initialEntries={['/upload']}>
        <App />
      </MemoryRouter>,
    );

    // 等待文档列表加载
    await waitFor(() => {
      expect(screen.getByText('贵州茅台2024年报.pdf')).toBeInTheDocument();
      expect(screen.getByText('比亚迪2024年报.pdf')).toBeInTheDocument();
    });
  });

  it('输入问题后发送 → 显示 RAG 回答和来源引用', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/upload']}>
        <App />
      </MemoryRouter>,
    );

    // 等待文档列表加载
    await screen.findByText('贵州茅台2024年报.pdf');

    // 点击选择文档
    await user.click(screen.getByText('贵州茅台2024年报.pdf'));

    // 输入问题
    const input = screen.getByPlaceholderText(/输入问题/);
    await user.type(input, '茅台2024年营收增长了多少？');

    // 发送
    await user.click(screen.getByRole('button', { name: /发送/ }));

    // 等待回答出现（回答和来源都有"营业收入"，用 getAllByText）
    await waitFor(() => {
      const matches = screen.getAllByText(/营业收入/);
      expect(matches.length).toBeGreaterThanOrEqual(2);
    });

    // 来源引用标签出现
    expect(screen.getByText('📎 来源引用')).toBeInTheDocument();
  });
});
