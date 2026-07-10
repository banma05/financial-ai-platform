import { http, HttpResponse } from 'msw';

/** 预设公司列表 */
export const MOCK_COMPANIES = [
  { code: '600519', name: '贵州茅台', short: '茅台' },
  { code: '002594', name: '比亚迪', short: '比亚迪' },
  { code: '300750', name: '宁德时代', short: '宁德' },
  { code: '000858', name: '五粮液', short: '五粮液' },
  { code: '600036', name: '招商银行', short: '招商' },
];

/** 模拟模板列表 */
export const MOCK_TEMPLATES = [
  { name: 'profitability', display_name: '盈利能力评估', description: '分析毛利率、净利率、ROE等', category: '综合分析' },
  { name: 'dupont', display_name: '杜邦分析', description: 'ROE三因子分解', category: '综合分析' },
  { name: 'growth', display_name: '成长性分析', description: '营收增长率、净利润增长率等', category: '综合分析' },
];

/** 模拟分析结果 */
export const MOCK_ANALYSIS_RESULT = {
  report: '## 营收分析报告\n\n贵州茅台2024年营收保持稳健增长...',
  charts: [],
  processing_time: 2.5,
  task_count: 6,
  clarification: null,
};

export const handlers = [
  // GET /api/v1/agent/templates
  http.get('/api/v1/agent/templates', () => {
    return HttpResponse.json(MOCK_TEMPLATES);
  }),

  // POST /api/v1/agent/analyze
  http.post('/api/v1/agent/analyze', async ({ request }) => {
    const body = await request.json() as { query: string; template?: string };
    // 验证请求参数
    if (!body.query || body.query.trim().length === 0) {
      return HttpResponse.json(
        { detail: 'query 不能为空' },
        { status: 422 },
      );
    }
    return HttpResponse.json({
      ...MOCK_ANALYSIS_RESULT,
      report: `## ${body.query}分析报告\n\n分析完成，耗时 2.5 秒。`,
    });
  }),
];
