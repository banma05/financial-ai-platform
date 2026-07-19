import { create } from 'zustand';

/** 分析模板 */
export interface Template {
  name: string;
  display_name: string;
  description: string;
  category: string;
}

/** 分析结果 */
export interface AnalysisResult {
  report: string;
  chartOptions: Array<{ option: Record<string, unknown>; description: string }>;
  processing_time: number;
  task_count: number;
  clarification: string | null;
}

/** 分析状态 */
interface AnalysisState {
  /** 当前选中的公司 */
  selectedCompany: string;
  /** 当前选中的模板 */
  selectedTemplate: string | null;
  /** 可用模板列表 */
  templates: Template[];
  /** 分析是否进行中 */
  isAnalyzing: boolean;
  /** 分析结果 */
  result: AnalysisResult | null;
  /** 错误信息 */
  error: string | null;

  // Actions
  setCompany: (company: string) => void;
  setTemplate: (template: string | null) => void;
  setTemplates: (templates: Template[]) => void;
  setAnalyzing: (loading: boolean) => void;
  setResult: (result: AnalysisResult | null) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  selectedCompany: '',
  selectedTemplate: null,
  templates: [],
  isAnalyzing: false,
  result: null,
  error: null,

  setCompany: (company) => set({ selectedCompany: company, result: null, error: null }),
  setTemplate: (template) => set({ selectedTemplate: template }),
  setTemplates: (templates) => set({ templates }),
  setAnalyzing: (isAnalyzing) => set({ isAnalyzing }),
  setResult: (result) => set({ result, isAnalyzing: false, error: null }),
  setError: (error) => set({ error, isAnalyzing: false }),
  reset: () => set({
    selectedCompany: '',
    selectedTemplate: null,
    isAnalyzing: false,
    result: null,
    error: null,
  }),
}));
