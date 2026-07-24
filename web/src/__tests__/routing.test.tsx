import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';

describe('页面路由', () => {
  it('默认路由 / 显示分析工作台页面', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 页面主标题
    const headings = screen.getAllByRole('heading', { name: '智能财务分析' });
    expect(headings.length).toBeGreaterThan(0);
  });

  it('点击"文档问答"导航切换到文档页面', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 点击侧边栏"文档问答"链接
    const links = screen.getAllByRole('link', { name: /文档问答/ });
    await user.click(links[0]);

    // 页面主标题变为"文档问答"
    expect(screen.getByRole('heading', { name: '文档问答' })).toBeInTheDocument();
  });

  it('两个页面间往返导航', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 首页 → 文档页
    await user.click(screen.getByRole('link', { name: /文档问答/ }));
    expect(screen.getByRole('heading', { name: '文档问答' })).toBeInTheDocument();

    // 文档页 → 首页
    await user.click(screen.getByRole('link', { name: /分析工作台/ }));
    const headings2 = screen.getAllByRole('heading', { name: '智能财务分析' });
    expect(headings2.length).toBeGreaterThan(0);
  });
});
