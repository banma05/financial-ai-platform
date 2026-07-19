import { NavLink, Outlet } from 'react-router-dom';

/** SVG 图标组件 */
const Icon = {
  Chart: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v18h18" />
      <path d="M7 16l4-8 4 4 4-6" />
    </svg>
  ),
  Doc: () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="12" y1="18" x2="12" y2="12" />
      <line x1="9" y1="15" x2="15" y2="15" />
    </svg>
  ),
  Sparkle: () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z" />
      <path d="M18 15l.8 2.2L21 18l-2.2.8L18 21l-.8-2.2L15 18l2.2-.8z" />
    </svg>
  ),
};

const navItems = [
  { to: '/', label: '分析工作台', icon: Icon.Chart },
  { to: '/upload', label: '文档问答', icon: Icon.Doc },
];

/**
 * 全局布局 — 现代化侧边栏 + 主内容区
 * V8.3: SVG 图标、左侧色条激活态、渐变品牌区
 */
export default function Layout() {
  return (
    <div className="flex h-screen bg-surface-base">
      {/* ── 侧边栏 ── */}
      <aside className="w-60 bg-white border-r border-border-default flex flex-col shrink-0">
        {/* 品牌区 */}
        <div className="px-5 py-5 border-b border-border-light">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-600 to-brand-400 flex items-center justify-center text-white shadow-sm">
              <Icon.Sparkle />
            </div>
            <div>
              <h1 className="text-sm font-bold text-gray-900 leading-tight">
                智能财务分析
              </h1>
              <p className="text-xs text-gray-400">AI-Powered Platform</p>
            </div>
          </div>
        </div>

        {/* 导航 */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-200 relative ${
                  isActive
                    ? 'bg-brand-50 text-brand-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {/* 左侧激活色条 */}
                  {isActive && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-brand-500 rounded-r-full" />
                  )}
                  <span className={isActive ? 'text-brand-600' : 'text-gray-400 group-hover:text-gray-500'}>
                    <item.icon />
                  </span>
                  <span>{item.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 底部信息 */}
        <div className="mx-3 mb-4 p-3 rounded-lg bg-gray-50 border border-border-light">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
            <span className="text-xs text-gray-500">系统运行中</span>
          </div>
          <p className="mt-1.5 text-xs text-gray-400">
            V8.3 · 智能财务分析平台
          </p>
        </div>
      </aside>

      {/* ── 主内容区 ── */}
      <main className="flex-1 overflow-auto">
        <div className="animate-fade-in">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
