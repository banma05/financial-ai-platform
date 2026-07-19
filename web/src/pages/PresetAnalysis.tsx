import { useEffect, useCallback, useState } from 'react';
import { api } from '@/api/client';
import { useAnalysisStore, type Template } from '@/stores/analysis';
import { useAnalysisStream } from '@/hooks/useAnalysisStream';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import ChartRenderer from '@/components/ChartRenderer';

/** 公司信息 */
interface CompanyInfo { code: string; name: string; short: string; hasPDF: boolean }
const _PDF_COMPANIES = new Set(['600519', '002594', '300750', '000858']);

/** 模板中文 → 图标映射 */
const TEMPLATE_ICONS: Record<string, string> = {
  profitability: '💰',
  dupont: '🔬',
  growth: '🚀',
};

/**
 * 预设分析页面 — 选择公司 + 模板 → 一键生成财务分析报告
 * V8.3: 全面美化 — 渐变标题、悬浮卡片、流式步骤可视化
 */
export default function PresetAnalysis() {
  const {
    selectedCompany, selectedTemplate, templates, isAnalyzing,
    result, error,
    setCompany, setTemplate, setTemplates, setAnalyzing, setResult, setError,
  } = useAnalysisStore();

  const [customQuery, setCustomQuery] = useState('');
  const [showResult, setShowResult] = useState(false);
  const [companies, setCompanies] = useState<CompanyInfo[]>([]);

  const { progress, startStream, abort } = useAnalysisStream();

  // 加载公司列表
  useEffect(() => {
    let cancelled = false;
    api.get<{ companies: { code: string; name: string }[] }>('/companies')
      .then((resp) => {
        if (cancelled) return;
        setCompanies(resp.companies.map((c) => ({
          ...c,
          short: c.name.replace(/[（(].*$/, ''),
          hasPDF: _PDF_COMPANIES.has(c.code),
        })));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // 加载模板列表
  useEffect(() => {
    if (templates.length > 0) return;
    let cancelled = false;
    api.get<Template[]>('/agent/templates')
      .then((data) => { if (!cancelled) setTemplates(data); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : '加载模板失败'); });
    return () => { cancelled = true; };
  }, [templates.length, setTemplates, setError]);

  // 流式分析
  const handleAnalyze = useCallback(async () => {
    if (!selectedCompany || isAnalyzing) return;
    const template = templates.find((t) => t.name === selectedTemplate);
    const query = customQuery.trim()
      ? (customQuery.includes(selectedCompany) ? customQuery.trim() : `${selectedCompany} ${customQuery.trim()}`)
      : `${selectedCompany} ${template?.display_name || '财务分析'}`;
    setAnalyzing(true);
    setShowResult(false);
    try { await startStream({ query, template: selectedTemplate || undefined }); }
    catch { /* SSE 错误由 progress.phase 处理 */ }
  }, [selectedCompany, selectedTemplate, customQuery, templates, isAnalyzing, setAnalyzing, startStream]);

  // 同步结果
  useEffect(() => {
    if (progress.phase === 'done' && progress.report && isAnalyzing) {
      setResult({
        report: progress.report,
        chartOptions: progress.chartOptions,
        processing_time: progress.processingTime ?? 0,
        task_count: progress.total,
        clarification: null,
      });
      setAnalyzing(false);
      setShowResult(true);
    }
    if (progress.phase === 'error' && isAnalyzing) {
      setError(progress.error || '分析失败');
      setAnalyzing(false);
    }
  }, [progress.phase, progress.report, progress.error, isAnalyzing, setResult, setAnalyzing, setError, setShowResult]);

  const handleCancel = useCallback(() => { abort(); setAnalyzing(false); }, [abort, setAnalyzing]);

  // 推荐问题 — 根据模板类型动态生成，无模板时给出通用建议
  const recommendedQuestions = (() => {
    if (!selectedCompany) return [];
    const company = selectedCompany;
    const year = `${new Date().getFullYear() - 1}年`;
    switch (selectedTemplate) {
      case 'profitability':
        return [`${company} ${year}毛利率、净利率、ROE分别是多少？`, `${company} ROE和ROA近三年变化趋势如何？`, `${company} 盈利能力在同行业中处于什么水平？`, `${company} ${year}营业收入和净利润的增速对比？`];
      case 'dupont':
        return [`${company} 杜邦三因子分解（净利率×周转率×杠杆）结果？`, `${company} ROE变化的主要驱动因素是哪个因子？`, `${company} 如何提升总资产周转率？`, `${company} 权益乘数变化对ROE的影响有多大？`];
      case 'growth':
        return [`${company} 近三年营收CAGR是多少？与行业均值对比？`, `${company} 净利润增长率趋势如何？是否存在波动？`, `${company} 营收增长是内生增长还是并购驱动？`, `${company} 未来三年营收增长预期如何？`];
      case null:  // 自由分析 — 通用问题
        return [`${company} ${year}年财务整体表现如何？`, `${company} ${year}年营收和利润增长了多少？`, `${company} 有哪些财务风险需要重点关注？`, `${company} 盈利能力和现金流质量如何？`];
      default:
        return [`${company} ${year}财务整体表现如何？`, `${company} ${year}营收同比增长了多少？`, `${company} 有哪些财务风险需要关注？`];
    }
  })();

  const canAnalyze = selectedCompany && !isAnalyzing;

  // ========== 结果视图 ==========
  if (showResult && result) {
    const handleExportPDF = () => window.print();
    const handleExportMD = () => {
      const blob = new Blob([result.report], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `分析报告-${selectedCompany || 'report'}.md`;
      a.click();
      URL.revokeObjectURL(url);
    };

    return (
      <div className="max-w-4xl mx-auto animate-fade-in-up">
        {/* 顶部工具栏 */}
        <div className="flex items-center justify-between mb-5">
          <button onClick={() => setShowResult(false)}
            className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700 font-medium transition-colors">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            返回重新分析
          </button>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400">
              ⏱ {result.processing_time.toFixed(1)}s · {result.task_count} 任务
            </span>
            <button onClick={handleExportPDF}
              className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all duration-200 flex items-center gap-1">
              🖨 导出PDF
            </button>
            <button onClick={handleExportMD}
              className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-all duration-200 flex items-center gap-1">
              📥 导出MD
            </button>
          </div>
        </div>

        <article className="card p-6 mb-4">
          <MarkdownRenderer content={result.report} />
        </article>

        {result.chartOptions.length > 0 && (
          <div className="card p-6 mb-4">
            <h2 className="text-lg font-semibold text-gray-800 mb-5 flex items-center gap-2">
              <span className="w-1 h-5 bg-brand-500 rounded-full" />
              可视化图表
            </h2>
            <div className="space-y-5">
              {result.chartOptions.map((item, i) => (
                <div key={`chart-${i}`} className="border border-border-default rounded-xl p-4 bg-surface-muted/50">
                  {item.description && (
                    <div className="mb-3 px-3 py-2 bg-brand-50 border border-brand-100 rounded-lg">
                      <p className="text-xs text-brand-700 leading-relaxed">
                        📊 <span className="font-medium">图表解读：</span>{item.description}
                      </p>
                    </div>
                  )}
                  <ChartRenderer option={item.option} />
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-green-400" />{result.processing_time.toFixed(1)} 秒</span>
          <span>{result.task_count} 个子任务</span>
        </div>
      </div>
    );
  }

  // ========== 分析表单视图 ==========
  return (
    <div className="max-w-4xl mx-auto animate-fade-in-up">
      {/* 页面标题 */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">预设分析</h1>
        <p className="mt-1.5 text-sm text-gray-500">
          选择公司，输入你想了解的问题（或选模板快速填充），AI 自动分析并生成报告
        </p>
      </div>

      {/* 步骤 1: 选择公司 */}
      <section className="mb-7">
        <div className="flex items-center gap-2 mb-3">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-brand-600 text-white text-xs font-bold">1</span>
          <h2 className="text-sm font-semibold text-gray-700">选择公司</h2>
          <span className="text-xs text-gray-400">({companies.filter(c => c.hasPDF).length} 家有年报 PDF)</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {companies.map((company) => (
            <button
              key={company.code}
              onClick={() => setCompany(company.name)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                selectedCompany === company.name
                  ? 'bg-brand-600 text-white shadow-md shadow-brand-200 scale-105'
                  : 'bg-white text-gray-600 border border-gray-200 hover:border-brand-300 hover:text-brand-600 hover:shadow-sm'
              }`}
            >
              {company.name}
              {company.hasPDF && <span className="ml-1 text-xs opacity-70" title="已有年报PDF">📥</span>}
            </button>
          ))}
        </div>
      </section>

      {/* 步骤 2: 分析模板（可选） */}
      <section className="mb-7">
        <div className="flex items-center gap-2 mb-3">
          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full border-2 border-dashed border-gray-300 text-gray-400 text-xs font-bold">2</span>
          <h2 className="text-sm font-semibold text-gray-700">分析模板</h2>
          <span className="text-xs text-gray-400 font-normal">（可选，点击选择分析框架）</span>
        </div>
        {templates.length === 0 ? (
          <div className="grid grid-cols-4 gap-3">
            {[1,2,3,4].map(i => <div key={i} className="skeleton h-20 rounded-xl" />)}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {/* 自由分析 — 默认不选模板 */}
            <button
              onClick={() => setTemplate(null)}
              className={`text-left p-4 rounded-xl border transition-all duration-200 ${
                !selectedTemplate
                  ? 'border-dashed border-brand-400 bg-brand-50/50 ring-1 ring-brand-200'
                  : 'border-dashed border-gray-200 bg-white hover:border-gray-300 hover:shadow-md hover:-translate-y-0.5'
              }`}
            >
              <div className="flex items-start justify-between">
                <h3 className={`font-semibold text-sm ${!selectedTemplate ? 'text-brand-700' : 'text-gray-800'}`}>
                  自由分析
                </h3>
                <span className="text-lg">🎯</span>
              </div>
              <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">
                不限框架，AI 根据你的问题自动选择分析维度
              </p>
            </button>
            {templates.map((template) => {
              const isActive = selectedTemplate === template.name;
              return (
                <button
                  key={template.name}
                  onClick={() => setTemplate(isActive ? null : template.name)}
                  className={`text-left p-4 rounded-xl border transition-all duration-200 group ${
                    isActive
                      ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-200 shadow-sm'
                      : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-md hover:-translate-y-0.5'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <h3 className={`font-semibold text-sm ${isActive ? 'text-brand-700' : 'text-gray-800'}`}>
                      {template.display_name}
                    </h3>
                    <span className="text-lg">{TEMPLATE_ICONS[template.name] || '📊'}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{template.description}</p>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* 推荐问题 */}
      {recommendedQuestions.length > 0 && (
        <section className="mb-7">
          <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
            💡 推荐问题<span className="text-xs text-gray-400 font-normal">（点击填入输入框）</span>
          </h2>
          <div className="flex flex-wrap gap-2">
            {recommendedQuestions.map((q, i) => (
              <button
                key={i}
                onClick={() => setCustomQuery(q)}
                className="px-3 py-1.5 rounded-full text-xs bg-brand-50 text-brand-700 border border-brand-200 hover:bg-brand-100 hover:border-brand-300 transition-all duration-200"
              >
                {q}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* 自定义问题 */}
      <section className="mb-7">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">
          自定义分析问题 <span className="text-xs text-gray-400 font-normal">（可选）</span>
        </h2>
        <div className="relative">
          <input
            type="text"
            value={customQuery}
            onChange={(e) => setCustomQuery(e.target.value)}
            aria-label="自定义分析问题"
            placeholder={`例如：${selectedCompany || '贵州茅台'} ${new Date().getFullYear() - 1}年营收同比增长了多少？`}
            className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm
              placeholder:text-gray-400
              focus:outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100
              transition-all duration-200"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round">
              <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/>
            </svg>
          </div>
        </div>
      </section>

      {/* 错误信息 */}
      {error && (
        <div className="mb-4 p-3.5 bg-danger-50 border border-red-200 rounded-xl text-sm text-danger-700 flex items-start gap-2">
          <span className="shrink-0 mt-0.5">⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {/* 流式分析进度 */}
      {isAnalyzing && progress.phase !== 'idle' && (
        <section className="mb-4 p-5 bg-gradient-to-br from-brand-50 to-blue-50 border border-brand-200 rounded-xl animate-fade-in">
          {/* 标题栏 */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-brand-800 flex items-center gap-2">
              {progress.phase === 'planning' && <><span className="spinner w-4 h-4 border-2 border-brand-400 border-t-transparent rounded-full" />正在规划分析步骤...</>}
              {progress.phase === 'executing' && <><span className="relative flex h-2.5 w-2.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75" /><span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-brand-500" /></span>{progress.currentTask || '执行中...'}</>}
              {progress.phase === 'done' && '✅ 分析完成'}
              {progress.phase === 'error' && '❌ 分析失败'}
            </span>
            <button onClick={handleCancel}
              className="text-xs text-gray-400 hover:text-danger-500 transition-colors font-medium">
              取消分析
            </button>
          </div>

          {/* 进度条 */}
          {progress.total > 0 && (
            <div className="w-full bg-brand-100 rounded-full h-2.5 mb-3 overflow-hidden">
              <div
                className="bg-gradient-to-r from-brand-500 to-brand-400 h-2.5 rounded-full transition-all duration-500 ease-out"
                style={{ width: `${Math.round((progress.completed / progress.total) * 100)}%` }}
              />
            </div>
          )}

          {/* 子任务列表 */}
          {progress.tasks.length > 0 && (
            <div className="space-y-1">
              {progress.tasks.map((t) => (
                <div key={t.id}
                  className={`flex items-center gap-2 text-xs py-1 px-2 rounded-md transition-colors ${
                    t.success ? 'text-green-700' : t.summary ? 'text-danger-700 bg-red-50/50' : 'text-gray-500'
                  }`}
                >
                  <span className="w-4 text-center">{t.success ? '✅' : t.summary ? '❌' : '⏳'}</span>
                  <span>{t.desc}</span>
                  {t.summary && <span className="text-gray-400 truncate ml-auto">— {t.summary}</span>}
                </div>
              ))}
            </div>
          )}

          {progress.phase === 'done' && (
            <p className="text-xs text-brand-600 mt-3 font-medium">
              总耗时 {progress.processingTime?.toFixed(1)} 秒 · {progress.total} 个子任务
            </p>
          )}
        </section>
      )}

      {/* 分析按钮 */}
      <div className={isAnalyzing ? 'hidden' : ''}>
        <button
          onClick={handleAnalyze}
          disabled={!canAnalyze}
          className={`w-full py-3.5 rounded-xl text-sm font-semibold transition-all duration-300 ${
            canAnalyze
              ? 'bg-gradient-to-r from-brand-600 to-brand-500 text-white shadow-lg shadow-brand-200 hover:shadow-xl hover:shadow-brand-300 hover:-translate-y-0.5 active:translate-y-0'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed'
          }`}
        >
          {canAnalyze
            ? (selectedTemplate
                ? `🚀 开始「${templates.find(t => t.name === selectedTemplate)?.display_name || ''}」分析`
                : '🚀 开始自由分析')
            : (selectedCompany ? '请输入问题或选择模板' : '请先选择一家公司')
          }
        </button>
        {canAnalyze && (
          <p className="text-center text-xs text-gray-400 mt-2">
            {selectedTemplate
              ? `将使用「${templates.find(t => t.name === selectedTemplate)?.display_name}」框架分析`
              : '自由分析模式：AI 根据你的问题自动选择分析维度'}
            {customQuery.trim() && ` · 已输入 ${customQuery.trim().length} 字自定义问题`}
          </p>
        )}
      </div>
    </div>
  );
}
