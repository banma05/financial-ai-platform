import { useEffect, useCallback, useState } from 'react';
import { apiClient } from '@/api/client';
import { useAnalysisStore, type Template } from '@/stores/analysis';
import MarkdownRenderer from '@/components/MarkdownRenderer';

/** 预设公司列表（前端常量，不调 API） */
const PRESET_COMPANIES = [
  { code: '600519', name: '贵州茅台', short: '茅台' },
  { code: '002594', name: '比亚迪', short: '比亚迪' },
  { code: '300750', name: '宁德时代', short: '宁德' },
  { code: '000858', name: '五粮液', short: '五粮液' },
  { code: '600036', name: '招商银行', short: '招商' },
];

/**
 * 预设分析页面 — 选择公司 + 模板 → 一键生成分析报告
 */
export default function PresetAnalysis() {
  const {
    selectedCompany,
    selectedTemplate,
    templates,
    isAnalyzing,
    result,
    error,
    setCompany,
    setTemplate,
    setTemplates,
    setAnalyzing,
    setResult,
    setError,
  } = useAnalysisStore();

  const [customQuery, setCustomQuery] = useState('');
  const [showResult, setShowResult] = useState(false);  // 本地视图切换，不清 store

  // 加载模板列表
  useEffect(() => {
    if (templates.length > 0) return; // 已加载则跳过
    apiClient
      .get('/agent/templates')
      .then((data) => setTemplates(data as unknown as Template[]))
      .catch(() => setError('加载模板失败'));
  }, [templates.length, setTemplates, setError]);

  // 开始分析
  const handleAnalyze = useCallback(async () => {
    if (!selectedCompany || isAnalyzing) return;

    const template = templates.find((t) => t.name === selectedTemplate);
    const query = customQuery.trim() || `${selectedCompany} ${template?.display_name || '财务分析'}`;

    setAnalyzing(true);
    setResult(null);
    setError(null);

    try {
      const data = await apiClient.post('/agent/analyze', {
        query,
        template: selectedTemplate || undefined,
        session_id: `preset-${Date.now()}`,
      });
      setResult(data as unknown as { report: string; charts: string[]; processing_time: number; task_count: number; clarification: string | null });
      setShowResult(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析请求失败');
    }
  }, [selectedCompany, selectedTemplate, customQuery, templates, isAnalyzing, setAnalyzing, setResult, setError]);

  // 能不能分析
  const canAnalyze = selectedCompany && !isAnalyzing;

  // 显示结果时
  if (showResult && result) {
    return (
      <div className="max-w-4xl mx-auto">
        <button
          onClick={() => setShowResult(false)}
          className="mb-4 text-sm text-blue-600 hover:underline"
        >
          ← 返回重新分析
        </button>
        <article className="bg-white rounded-xl p-6 shadow-sm border">
          <MarkdownRenderer content={result.report} />
        </article>
        {result.charts.length > 0 && (
          <div className="mt-4 bg-white rounded-xl p-6 shadow-sm border">
            <p className="text-sm text-gray-500">图表 ({result.charts.length} 张)</p>
          </div>
        )}
        <p className="mt-2 text-xs text-gray-400">
          处理耗时 {result.processing_time.toFixed(1)} 秒 · {result.task_count} 个子任务
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">预设分析</h1>
      <p className="text-gray-500 mb-6">选择公司和分析模板，一键生成财务分析报告。</p>

      {/* 公司标签 */}
      <section className="mb-6">
        <h2 className="text-sm font-medium text-gray-600 mb-3">选择公司</h2>
        <div className="flex flex-wrap gap-2">
          {PRESET_COMPANIES.map((company) => (
            <button
              key={company.code}
              onClick={() => setCompany(company.name)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                selectedCompany === company.name
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-white text-gray-700 border border-gray-200 hover:border-blue-300 hover:text-blue-600'
              }`}
            >
              {company.name}
            </button>
          ))}
        </div>
      </section>

      {/* 分析模板卡片 */}
      <section className="mb-6">
        <h2 className="text-sm font-medium text-gray-600 mb-3">分析模板</h2>
        {templates.length === 0 ? (
          <p className="text-sm text-gray-400">加载模板中...</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {templates.map((template) => (
              <button
                key={template.name}
                onClick={() => setTemplate(template.name)}
                className={`text-left p-4 rounded-xl border transition-colors ${
                  selectedTemplate === template.name
                    ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-200'
                    : 'border-gray-200 bg-white hover:border-gray-300'
                }`}
              >
                <h3 className="font-medium text-sm">{template.display_name}</h3>
                <p className="text-xs text-gray-500 mt-1">{template.description}</p>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* 自定义问题输入 */}
      <section className="mb-6">
        <h2 className="text-sm font-medium text-gray-600 mb-3">自定义分析问题（可选）</h2>
        <input
          type="text"
          value={customQuery}
          onChange={(e) => setCustomQuery(e.target.value)}
          placeholder={`例如：${selectedCompany ? selectedCompany : '贵州茅台'} 2024年营收同比增长了多少？`}
          className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-200"
        />
      </section>

      {/* 错误信息 */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* 分析按钮 */}
      <button
        onClick={handleAnalyze}
        disabled={!canAnalyze}
        className={`w-full py-3 rounded-xl text-sm font-medium transition-colors ${
          canAnalyze
            ? 'bg-blue-600 text-white hover:bg-blue-700'
            : 'bg-gray-200 text-gray-400 cursor-not-allowed'
        } ${isAnalyzing ? 'animate-pulse' : ''}`}
      >
        {isAnalyzing ? '分析中...' : '开始分析'}
      </button>
    </div>
  );
}

