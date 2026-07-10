import { Routes, Route } from 'react-router-dom';
import Layout from '@/components/Layout';
import PresetAnalysis from '@/pages/PresetAnalysis';
import DocumentUpload from '@/pages/DocumentUpload';
import ReportView from '@/pages/ReportView';

/**
 * 应用根组件 — 路由配置
 * BrowserRouter 在 main.tsx 中提供，测试中使用 MemoryRouter
 */
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<PresetAnalysis />} />
        <Route path="upload" element={<DocumentUpload />} />
        <Route path="report" element={<ReportView />} />
      </Route>
    </Routes>
  );
}
