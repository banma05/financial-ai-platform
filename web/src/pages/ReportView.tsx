import { useAnalysisStore } from '@/stores/analysis';
import MarkdownRenderer from '@/components/MarkdownRenderer';

/**
 * 报告展示页面 — Markdown 渲染 + ECharts 图表 + 元信息
 */
export default function ReportView() {
  const { result, selectedCompany, selectedTemplate } = useAnalysisStore();

  // 无结果时的空状态
  if (!result) {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <div className="text-5xl mb-4">📋</div>
        <h1 className="text-2xl font-bold mb-2">暂无分析结果</h1>
        <p className="text-gray-500 mb-6">
          先去"预设分析"页面选择公司和模板，生成一份分析报告。
        </p>
        <a
          href="/"
          className="inline-block px-5 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          去分析 →
        </a>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* 顶部信息栏 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">分析报告</h1>
          {selectedCompany && (
            <p className="text-sm text-gray-500 mt-1">
              {selectedCompany}
              {selectedTemplate && ` · ${selectedTemplate}`}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex gap-4 text-xs text-gray-400">
            <span>⏱ {result.processing_time.toFixed(1)} 秒</span>
            <span>📝 {result.task_count} 个子任务</span>
          </div>
          {/* 导出按钮 */}
          <button
            onClick={() => window.print()}
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors"
          >
            🖨 打印/导出PDF
          </button>
          <button
            onClick={() => {
              const blob = new Blob([result.report], { type: 'text/markdown;charset=utf-8' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `分析报告-${selectedCompany || 'report'}.md`;
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-white hover:bg-gray-50 transition-colors"
          >
            📥 导出文本
          </button>
        </div>
      </div>

      {/* Markdown 报告正文 */}
      <section className="bg-white rounded-xl p-6 shadow-sm border mb-6">
        <MarkdownRenderer content={result.report} />
      </section>

      {/* 图表区域 */}
      {result.charts && result.charts.length > 0 && (
        <section className="bg-white rounded-xl p-6 shadow-sm border mb-6">
          <h2 className="text-lg font-semibold mb-4">📈 可视化图表</h2>
          <div className="space-y-4">
            {result.charts.map((chartData, i) => (
              <div key={`chart-${i}`} className="border rounded-lg p-4">
                {/* V8.1 D7: 后端始终生成 base64 图片，移除 ECharts 死代码 */}
                <img src={chartData} alt={`图表 ${i + 1}`} className="max-w-full" />
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 追问提示 */}
      {result.clarification && (
        <section className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="text-sm text-amber-800">
            💡 {result.clarification}
          </p>
        </section>
      )}
    </div>
  );
}
