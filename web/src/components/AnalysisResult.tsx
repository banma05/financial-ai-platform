import MarkdownRenderer from '@/components/MarkdownRenderer';
import ChartRenderer from '@/components/ChartRenderer';

interface ChartItem { option: any; description?: string }

interface AnalysisResultProps {
  report: string;
  chartOptions: ChartItem[];
  processingTime: number;
  taskCount: number;
  selectedCompany: string | null;
  onBack: () => void;
}

export default function AnalysisResult({
  report, chartOptions, processingTime, taskCount, selectedCompany, onBack,
}: AnalysisResultProps) {
  const handleExportPDF = () => window.print();
  const handleExportMD = () => {
    const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `分析报告-${selectedCompany || 'report'}.md`;
    a.click(); URL.revokeObjectURL(url);
  };

  return (
    <div className="max-w-4xl mx-auto animate-fade-in-up">
      {/* 顶部工具栏 — 玻璃态 */}
      <div className="sticky top-4 z-10 flex items-center justify-between mb-6 p-3 rounded-2xl
        bg-white/80 backdrop-blur-xl border border-white/20 shadow-lg shadow-slate-200/50">
        <button onClick={onBack}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-xl bg-slate-100
            text-slate-600 hover:bg-slate-200 hover:text-slate-800 font-medium transition-all duration-200">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          返回
        </button>

        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-medium">
            ⏱ {processingTime.toFixed(1)}s · {taskCount} 任务
          </span>
          <div className="flex gap-1.5">
            <button onClick={handleExportPDF}
              className="px-3 py-1.5 text-xs rounded-lg bg-white border border-slate-200 text-slate-600
                hover:bg-slate-50 hover:border-slate-300 transition-all duration-200 flex items-center gap-1.5 shadow-sm">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              导出PDF
            </button>
            <button onClick={handleExportMD}
              className="px-3 py-1.5 text-xs rounded-lg bg-gradient-to-r from-indigo-600 to-indigo-500 text-white
                hover:from-indigo-700 hover:to-indigo-600 transition-all duration-200 flex items-center gap-1.5 shadow-sm shadow-indigo-200">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              导出MD
            </button>
          </div>
        </div>
      </div>

      {/* 报告正文 */}
      <article className="rounded-2xl bg-white border border-slate-200/60 shadow-xl shadow-slate-200/30 p-8 mb-6
        prose prose-slate max-w-none prose-headings:text-slate-800 prose-h2:text-lg prose-h2:font-semibold
        prose-p:text-slate-600 prose-table:text-sm">
        <MarkdownRenderer content={report} />
      </article>

      {/* 图表 */}
      {chartOptions.length > 0 && (
        <div className="rounded-2xl bg-white border border-slate-200/60 shadow-xl shadow-slate-200/30 p-8 mb-6">
          <h2 className="text-lg font-semibold text-slate-800 mb-6 flex items-center gap-2">
            <span className="w-1 h-5 bg-gradient-to-b from-indigo-500 to-violet-500 rounded-full" />
            可视化图表
          </h2>
          <div className="space-y-6">
            {chartOptions.map((item, i) => (
              <div key={`chart-${i}`}
                className="border border-slate-100 rounded-xl p-5 bg-gradient-to-br from-slate-50 to-white">
                {item.description && (
                  <div className="mb-4 px-4 py-3 bg-indigo-50/80 border border-indigo-100 rounded-xl">
                    <p className="text-sm text-indigo-700 leading-relaxed">
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
    </div>
  );
}
