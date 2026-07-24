import type { Template } from '@/stores/analysis';

interface CompanyInfo { code: string; name: string; short: string; hasPDF: boolean }

interface AnalysisFormProps {
  selectedCompany: string | null; selectedTemplate: string | null;
  customQuery: string; isAnalyzing: boolean;
  companies: CompanyInfo[]; templates: Template[];
  recommendedQuestions: string[]; error: string | null;
  onSelectCompany: (name: string) => void;
  onSelectTemplate: (name: string | null) => void;
  onQueryChange: (query: string) => void;
  onAnalyze: () => void;
}

const TEMPLATE_ICONS: Record<string, string> = {
  profitability: '💰', dupont: '🔬', growth: '🚀', cash_flow: '💵',
  risk_scan: '🛡️', cross_company_profit: '⚖️', multi_dimension: '📊',
  valuation: '📈', operating: '⚙️', cost_analysis: '📋', industry_compare: '🏭',
};

export default function AnalysisForm({
  selectedCompany, selectedTemplate, customQuery, isAnalyzing,
  companies, templates, recommendedQuestions, error,
  onSelectCompany, onSelectTemplate, onQueryChange, onAnalyze,
}: AnalysisFormProps) {
  const canAnalyze = selectedCompany && !isAnalyzing;
  const year = new Date().getFullYear() - 1;

  return (
    <div className="max-w-4xl mx-auto animate-fade-in-up">
      {/* 页面标题 — 渐变文字 + 光晕背景 */}
      <div className="relative mb-10 text-center">
        <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[500px] h-[300px] bg-gradient-to-b from-indigo-500/8 via-violet-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />
        <h1 className="relative text-3xl font-bold">
          <span className="bg-gradient-to-r from-slate-800 via-indigo-700 to-slate-800 bg-clip-text text-transparent">
            智能财务分析
          </span>
        </h1>
        <p className="relative mt-2 text-sm text-slate-500">
          选择公司 → 选模板或输入问题 → AI 自动生成专业分析报告
        </p>
      </div>

      {/* 步骤 1: 选择公司 — 玻璃态标签 */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-lg bg-indigo-600 text-white text-xs font-bold shadow-sm shadow-indigo-200">1</span>
          <h2 className="text-sm font-semibold text-slate-700">选择分析公司</h2>
          <span className="text-xs text-slate-400">({companies.filter(c => c.hasPDF).length} 家有年报PDF)</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {companies.map((company) => {
            const active = selectedCompany === company.name;
            return (
              <button key={company.code} onClick={() => onSelectCompany(company.name)}
                className={`relative px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 ${
                  active
                    ? 'bg-gradient-to-br from-indigo-600 to-indigo-500 text-white shadow-lg shadow-indigo-200 scale-[1.03]'
                    : 'bg-white/80 backdrop-blur-sm text-slate-600 border border-slate-200/80 hover:border-indigo-300 hover:text-indigo-600 hover:shadow-md hover:bg-white'
                }`}
              >
                {company.name}
                {company.hasPDF && <span className="ml-1.5 text-xs opacity-80" title="已有年报PDF">📄</span>}
              </button>
            );
          })}
        </div>
      </section>

      {/* 步骤 2: 分析模板 — 悬浮卡片 + 发光选中态 */}
      <section className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <span className="inline-flex items-center justify-center w-6 h-6 rounded-lg border-2 border-dashed border-slate-300 text-slate-400 text-xs font-bold">2</span>
          <h2 className="text-sm font-semibold text-slate-700">选择分析框架</h2>
          <span className="text-xs text-slate-400">（可选）</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {/* 自由分析 */}
          <button onClick={() => onSelectTemplate(null)}
            className={`text-left p-4 rounded-xl border-2 border-dashed transition-all duration-300 group ${
              !selectedTemplate
                ? 'border-indigo-400 bg-indigo-50/80 ring-4 ring-indigo-100/50'
                : 'border-slate-200 bg-white/60 hover:border-slate-300 hover:bg-white hover:shadow-lg hover:-translate-y-0.5'
            }`}
          >
            <div className="flex items-start justify-between">
              <h3 className={`font-semibold text-sm ${!selectedTemplate ? 'text-indigo-700' : 'text-slate-700'}`}>自由分析</h3>
              <span className="text-xl">🎯</span>
            </div>
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">AI 根据你的问题自动选择最佳分析维度</p>
          </button>
          {templates.map((template) => {
            const isActive = selectedTemplate === template.name;
            return (
              <button key={template.name} onClick={() => onSelectTemplate(isActive ? null : template.name)}
                className={`relative text-left p-4 rounded-xl border transition-all duration-300 group ${
                  isActive
                    ? 'border-indigo-500 bg-gradient-to-br from-indigo-50 to-violet-50 ring-2 ring-indigo-200 shadow-lg shadow-indigo-100 -translate-y-0.5'
                    : 'border-slate-200 bg-white/60 hover:border-slate-300 hover:bg-white hover:shadow-lg hover:-translate-y-0.5'
                }`}
              >
                {isActive && (
                  <div className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center shadow-sm">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="4"><polyline points="20 6 9 17 4 12"/></svg>
                  </div>
                )}
                <div className="flex items-start justify-between">
                  <h3 className={`font-semibold text-sm ${isActive ? 'text-indigo-700' : 'text-slate-700'}`}>{template.display_name}</h3>
                  <span className="text-lg">{TEMPLATE_ICONS[template.name] || '📊'}</span>
                </div>
                <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">{template.description}</p>
              </button>
            );
          })}
        </div>
      </section>

      {/* 推荐问题 — 渐变标签 */}
      {recommendedQuestions.length > 0 && (
        <section className="mb-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
            💡 推荐问题
            <span className="text-xs text-slate-400 font-normal">（点击填入）</span>
          </h2>
          <div className="flex flex-wrap gap-2">
            {recommendedQuestions.map((q, i) => (
              <button key={i} onClick={() => onQueryChange(q)}
                className="px-3.5 py-1.5 rounded-full text-xs font-medium
                  bg-gradient-to-r from-indigo-50 to-violet-50 text-indigo-700
                  border border-indigo-200/80 hover:border-indigo-400 hover:from-indigo-100 hover:to-violet-100
                  hover:shadow-sm hover:-translate-y-0.5 transition-all duration-200">
                {q}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* 自定义问题 — 发光输入框 */}
      <section className="mb-6">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">
          自定义分析问题 <span className="text-xs text-slate-400 font-normal">（可选）</span>
        </h2>
        <div className="relative group">
          <div className="absolute -inset-0.5 bg-gradient-to-r from-indigo-500 to-violet-500 rounded-xl opacity-0 group-focus-within:opacity-100 blur transition duration-300" />
          <input type="text" value={customQuery} onChange={(e) => onQueryChange(e.target.value)}
            aria-label="自定义分析问题"
            placeholder={`例如：${selectedCompany || '贵州茅台'} ${year}年营收同比增长了多少？`}
            className="relative w-full px-4 py-3.5 bg-white border border-slate-200 rounded-xl text-sm
              placeholder:text-slate-400 focus:outline-none focus:border-transparent
              transition-all duration-200 shadow-sm"
          />
        </div>
      </section>

      {/* 错误信息 */}
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 flex items-start gap-2.5 animate-fade-in">
          <span className="shrink-0 mt-0.5">⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {/* 分析按钮 — 渐变动画 */}
      <div className="mt-8">
        <button onClick={onAnalyze} disabled={!canAnalyze}
          className={`relative w-full py-4 rounded-xl text-sm font-semibold transition-all duration-500 overflow-hidden ${
            canAnalyze
              ? 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 text-white shadow-xl shadow-indigo-200/50 hover:shadow-2xl hover:shadow-indigo-300/50 hover:-translate-y-0.5 active:translate-y-0 bg-[length:100%] hover:bg-[length:150%]'
              : 'bg-slate-100 text-slate-400 cursor-not-allowed'
          }`}
        >
          <span className="relative z-10">
            {canAnalyze
              ? (selectedTemplate
                  ? `🚀 开始「${templates.find(t => t.name === selectedTemplate)?.display_name || ''}」分析`
                  : '🚀 开始智能分析')
              : (selectedCompany ? '请输入问题或选择模板' : '👆 请先选择一家公司')
            }
          </span>
        </button>
        {canAnalyze && (
          <p className="text-center text-xs text-slate-400 mt-3">
            {selectedTemplate
              ? `使用「${templates.find(t => t.name === selectedTemplate)?.display_name}」框架 · 数据驱动分析`
              : '自由分析模式 · AI 自主选择最佳分析维度'}
            {customQuery.trim() && ` · ${customQuery.trim().length} 字自定义问题`}
          </p>
        )}
      </div>
    </div>
  );
}
