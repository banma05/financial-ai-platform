import { NavLink, Outlet } from 'react-router-dom';

const navItems = [
  { to: '/', label: '预设分析', icon: '📊' },
  { to: '/upload', label: '文档上传', icon: '📄' },
  { to: '/report', label: '报告展示', icon: '📋' },
];

/**
 * 全局布局 — 侧边栏导航 + 主内容区
 */
export default function Layout() {
  return (
    <div className="flex h-screen bg-gray-50">
      {/* 侧边栏 */}
      <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-100">
          <h1 className="text-lg font-bold text-blue-600">📈 智能财务分析</h1>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-600 hover:bg-gray-100'
                }`
              }
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-gray-100 text-xs text-gray-400">
          V8.0 · 智能财务分析平台
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
