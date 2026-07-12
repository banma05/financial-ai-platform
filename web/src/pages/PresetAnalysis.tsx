import { useEffect, useCallback, useState } from 'react';
import { api } from '@/api/client';
import { useAnalysisStore, type Template, type AnalysisResult } from '@/stores/analysis';
import MarkdownRenderer from '@/components/MarkdownRenderer';

/** 公司信息 */
interface CompanyInfo { code: string; name: string; short: string; hasPDF: boolean }
// V8.1 D17: hasPDF 静态对照表（API 返回的公司是否在知识库中有 PDF 年报）
const _PDF_COMPANIES = new Set(['600519', '002594', '300750', '000858']);

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
  const [companies, setCompanies] = useState<CompanyInfo[]>([]);

  // V8.1 D17: 从后端 API 动态获取公司列表
  useEffect(() => {
    let cancelled = false;
    api.get<{ companies: { code: string; name: string }[] }>('/companies')
      .then((resp) => {
        if (cancelled) return;
        setCompanies(resp.companies.map((c) => ({
          ...c,
          short: c.name.replace(/[（(].*$/, ''),  // 用完整名称作为简称
          hasPDF: _PDF_COMPANIES.has(c.code),
        })));
      })
      .catch(() => { /* 网络不可用时使用空列表，不崩溃 */ });
    return () => { cancelled = true; };
  }, []);

  // 加载模板列表
  useEffect(() => {
    if (templates.length > 0) return; // 已加载则跳过
    let cancelled = false;
    api.get<Template[]>('/agent/templates')
      .then((data) => { if (!cancelled) setTemplates(data); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : '加载模板失败'); });
    return () => { cancelled = true; };
  }, [templates.length, setTemplates, setError]);

  // 开始分析
  const handleAnalyze = useCallback(async () => {
    if (!selectedCompany || isAnalyzing) return;

    const template = templates.find((t) => t.name === selectedTemplate);
    const query = customQuery.trim() || `${selectedCompany} ${template?.display_name || '财务分析'}`;

    setAnalyzing(true);

    try {
      const data = await api.post<AnalysisResult>('/agent/analyze', {
        query,
        template: selectedTemplate || undefined,
        session_id: `preset-${Date.now()}`,
      });
      setResult(data);
      setShowResult(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '分析请求失败');
    }
  }, [selectedCompany, selectedTemplate, customQuery, templates, isAnalyzing, setAnalyzing, setResult, setError]);

  // 推荐分析问题（根据公司+模板动态生成）
  const recommendedQuestions = (() => {
    if (!selectedCompany) return [];
    const company = selectedCompany;
    // V8.1 D18: 使用当前年份，不再硬编码 2024年
    const year = `${new Date().getFullYear()}年`;

    switch (selectedTemplate) {
      case 'profitability':
        return [
          `${company} ${year}毛利率、净利率分别是多少？`,
          `${company} ROE和ROA变化趋势如何？`,
          `${company} 盈利能力在同行业中处于什么水平？`,
          `${company} ${year}营业收入和净利润增长率对比？`,
        ];
      case 'dupont':
        return [
          `${company} 杜邦三因子分解结果？`,
          `${company} ROE的主要驱动因素是什么？`,
          `${company} 如何提升资产周转率？`,
          `${company} 权益乘数变化对ROE的影响有多大？`,
        ];
      case 'growth':
        return [
          `${company} 近三年营收CAGR是多少？`,
          `${company} 净利润增长率趋势如何？`,
          `${company} 营收增长是内生的还是并购驱动？`,
          `${company} 未来三年营收增长预期？`,
        ];
      default:
        return [
          `${company} ${year}财务整体表现如何？`,
          `${company} ${year}营收同比增长了多少？`,
          `${company} 有哪些财务风险需要关注？`,
        ];
    }
  })();

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
        <h2 className="text-sm font-medium text-gray-600 mb-3">
          选择公司
          <span className="ml-2 text-xs text-gray-400 font-normal">
            ({companies.filter(c => c.hasPDF).length}家有年报PDF可用)
          </span>
        </h2>
        <div className="flex flex-wrap gap-2">
          {companies.map((company) => (
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
              {company.hasPDF && (
                <span className="ml-1 text-xs opacity-70" title="已有年报PDF">📥</span>
              )}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-gray-400">
          带 📥 的公司已有年报PDF，可在
          <a href="/upload" className="text-blue-500 hover:underline mx-0.5">文档上传</a>
          页面上传后做 RAG 问答分析
        </p>
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

      {/* 推荐问题 */}
      {recommendedQuestions.length > 0 && (
        <section className="mb-6">
          <h2 className="text-sm font-medium text-gray-600 mb-3">
            💡 推荐问题（点击填入）
          </h2>
          <div className="flex flex-wrap gap-2">
            {recommendedQuestions.map((q, i) => (
              <button
                key={i}
                onClick={() => setCustomQuery(q)}
                className="px-3 py-1.5 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* 自定义问题输入 */}
      <section className="mb-6">
        <h2 className="text-sm font-medium text-gray-600 mb-3">自定义分析问题（可选）</h2>
        <input
          type="text"
          value={customQuery}
          onChange={(e) => setCustomQuery(e.target.value)}
          aria-label="自定义分析问题"
          placeholder={`例如：${selectedCompany ? selectedCompany : '贵州茅台'} ${new Date().getFullYear()}年营收同比增长了多少？`}
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

