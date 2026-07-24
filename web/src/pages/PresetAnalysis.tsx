import { useEffect, useCallback, useState, useMemo } from 'react';
import { api } from '@/api/client';
import { useAnalysisStore, type Template } from '@/stores/analysis';
import { useAnalysisStream } from '@/hooks/useAnalysisStream';
import AnalysisForm from '@/components/AnalysisForm';
import AnalysisProgress from '@/components/AnalysisProgress';
import AnalysisResult from '@/components/AnalysisResult';

/** 公司信息 */
interface CompanyInfo { code: string; name: string; short: string; hasPDF: boolean }
const _PDF_COMPANIES = new Set(['600519', '002594', '300750', '000858']);

/**
 * 预设分析页面 — 编排者模式: Form → Progress → Result 三视图切换
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
        chartOptions: progress.chartOptions || [],
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

  // 推荐问题
  const recommendedQuestions = useMemo(() => {
    if (!selectedCompany) return [];
    const company = selectedCompany;
    const year = `${new Date().getFullYear() - 1}年`;
    const qs: Record<string, string[]> = {
      profitability: [`${company} ${year}毛利率、净利率、ROE分别是多少？`, `${company} ROE和ROA近三年变化趋势如何？`, `${company} 盈利能力在同行业中处于什么水平？`],
      dupont: [`${company} 杜邦三因子分解（净利率×周转率×杠杆）结果？`, `${company} ROE变化的主要驱动因素是哪个因子？`],
      growth: [`${company} 近三年营收CAGR是多少？与行业均值对比？`, `${company} 净利润增长率趋势如何？是否有波动？`],
      cash_flow: [`${company} ${year}经营现金流健康吗？`, `${company} 自由现金流是正还是负？`],
      risk_scan: [`${company} ${year}财务风险整体评估`, `${company} 资产负债率、流动比率是否健康？`],
      valuation: [`${company} 当前PE/PB估值水平如何？`, `${company} 估值与同行业对比如何？`],
      cost_analysis: [`${company} ${year}四费结构是否合理？`, `${company} 研发费用投入力度够不够？`],
    };
    return qs[selectedTemplate || ''] || [`${company} ${year}年财务整体表现如何？`, `${company} ${year}年营收和利润增长了多少？`, `${company} 有哪些财务风险需要重点关注？`];
  }, [selectedCompany, selectedTemplate]);

  // ── 结果视图 ──
  if (showResult && result) {
    return (
      <AnalysisResult
        report={result.report}
        chartOptions={result.chartOptions || []}
        processingTime={result.processing_time}
        taskCount={result.task_count}
        selectedCompany={selectedCompany}
        onBack={() => setShowResult(false)}
      />
    );
  }

  // ── 进度视图 ──
  if (isAnalyzing && progress.phase !== 'idle') {
    return <AnalysisProgress progress={progress} onCancel={handleCancel} />;
  }

  // ── 表单视图 ──
  return (
    <AnalysisForm
      selectedCompany={selectedCompany}
      selectedTemplate={selectedTemplate}
      customQuery={customQuery}
      isAnalyzing={isAnalyzing}
      companies={companies}
      templates={templates}
      recommendedQuestions={recommendedQuestions}
      error={error}
      onSelectCompany={setCompany}
      onSelectTemplate={setTemplate}
      onQueryChange={setCustomQuery}
      onAnalyze={handleAnalyze}
    />
  );
}
