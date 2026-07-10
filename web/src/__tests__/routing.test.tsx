import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';

describe('页面路由', () => {
  it('默认路由 / 显示预设分析页面', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 页面主标题为"预设分析"
    expect(screen.getByRole('heading', { name: '预设分析' })).toBeInTheDocument();
  });

  it('点击"文档上传"导航切换到上传页面', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 点击侧边栏"文档上传"链接
    await user.click(screen.getByRole('link', { name: /文档上传/ }));

    // 页面主标题变为"文档上传"
    expect(screen.getByRole('heading', { name: '文档上传' })).toBeInTheDocument();
  });

  it('点击"报告展示"导航切换到报告页面', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );

    // 点击侧边栏"报告展示"链接
    await user.click(screen.getByRole('link', { name: /报告展示/ }));

    // 页面主标题变为"分析报告"
    expect(screen.getByRole('heading', { name: '分析报告' })).toBeInTheDocument();
  });
});
