interface TaskItem { id: string; desc: string; success?: boolean; summary?: string }

interface StreamProgress {
  phase: string; completed: number; total: number;
  currentTask?: string; tasks: TaskItem[];
  processingTime?: number; error?: string;
}

interface AnalysisProgressProps {
  progress: StreamProgress;
  onCancel: () => void;
}

export default function AnalysisProgress({ progress, onCancel }: AnalysisProgressProps) {
  const pct = progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0;
  const isRunning = progress.phase !== 'done' && progress.phase !== 'error';

  return (
    <div className="max-w-2xl mx-auto animate-fade-in-up">
      {/* 状态卡片 */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 p-8 text-white shadow-2xl shadow-indigo-500/20">
        {/* 背景光晕 */}
        <div className="absolute -top-20 -right-20 w-64 h-64 bg-indigo-500/20 rounded-full blur-3xl" />
        <div className="absolute -bottom-20 -left-20 w-48 h-48 bg-violet-500/15 rounded-full blur-3xl" />

        <div className="relative">
          {/* 状态标题 */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              {isRunning ? (
                <div className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-400" />
                </div>
              ) : progress.phase === 'done' ? (
                <span className="text-2xl">✅</span>
              ) : (
                <span className="text-2xl">❌</span>
              )}
              <span className="text-lg font-semibold">
                {progress.phase === 'planning' && '正在规划分析步骤...'}
                {progress.phase === 'executing' && (progress.currentTask || '执行分析中...')}
                {progress.phase === 'done' && '分析完成'}
                {progress.phase === 'error' && '分析失败'}
              </span>
            </div>
            {isRunning && (
              <button onClick={onCancel}
                className="px-3 py-1.5 text-xs rounded-lg bg-white/10 hover:bg-white/20 text-white/80 hover:text-white transition-all duration-200 backdrop-blur-sm border border-white/10">
                取消
              </button>
            )}
          </div>

          {/* 进度条 */}
          <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden mb-5 backdrop-blur-sm">
            <div
              className="h-full rounded-full transition-all duration-700 ease-out"
              style={{
                width: `${pct}%`,
                background: isRunning
                  ? 'linear-gradient(90deg, #818cf8, #a78bfa, #c084fc)'
                  : progress.phase === 'done'
                    ? 'linear-gradient(90deg, #34d399, #10b981)'
                    : 'linear-gradient(90deg, #f87171, #ef4444)',
              }}
            />
          </div>

          {/* 百分比 */}
          <div className="text-center mb-5">
            <span className="text-4xl font-bold bg-gradient-to-r from-indigo-300 to-violet-300 bg-clip-text text-transparent">
              {pct}%
            </span>
          </div>

          {/* 任务列表 */}
          {progress.tasks.length > 0 && (
            <div className="space-y-1.5">
              {progress.tasks.map((t) => (
                <div key={t.id}
                  className={`flex items-center gap-2.5 text-sm py-1.5 px-3 rounded-lg transition-all duration-300 ${
                    t.success ? 'bg-emerald-500/10 text-emerald-300' :
                    t.summary ? 'bg-red-500/10 text-red-300' : 'text-white/50'
                  }`}
                >
                  <span className="w-5 text-center text-xs">
                    {t.success ? '✓' : t.summary ? '✗' : '⋯'}
                  </span>
                  <span className="flex-1">{t.desc}</span>
                  {t.summary && <span className="text-white/30 text-xs truncate max-w-[200px]">{t.summary}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 完成时统计 */}
      {progress.phase === 'done' && progress.processingTime && (
        <div className="flex justify-center gap-6 mt-4 text-sm text-slate-400">
          <span>⏱ {progress.processingTime.toFixed(1)}s</span>
          <span>📋 {progress.total} 个子任务</span>
        </div>
      )}
    </div>
  );
}
