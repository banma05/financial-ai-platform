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
  chartOptions: [] as Array<{ option: Record<string, unknown>; description: string }>,
  processing_time: 2.5,
  task_count: 6,
  clarification: null,
};

/** 模拟文档列表 */
export const MOCK_DOCUMENTS = [
  { filename: '贵州茅台2024年报.pdf', chunk_count: 856, page_count: 198, file_size: 2048000, upload_time: '2026-07-01 10:30' },
  { filename: '比亚迪2024年报.pdf', chunk_count: 723, page_count: 165, file_size: 1835000, upload_time: '2026-07-02 14:20' },
];

/** 模拟 RAG 回答 */
export const MOCK_CHAT_RESPONSE = {
  answer: '根据年报数据，贵州茅台2024年营业收入同比增长约15%...',
  sources: [
    { content: '2024年公司实现营业收入1,509.47亿元，同比增长15.23%...', source: '贵州茅台2024年报.pdf', page: 5, score: 0.92 },
    { content: '毛利率达到91.96%，同比提升0.21个百分点...', source: '贵州茅台2024年报.pdf', page: 8, score: 0.87 },
  ],
  processing_time: 0.35,
};

export const handlers = [
  // ── V8.1 D17: 公司列表 API ──
  http.get('/api/v1/companies', () => {
    return HttpResponse.json({
      companies: MOCK_COMPANIES.map(({ code, name }) => ({ code, name })),
    });
  }),

  // ── Agent API ──
  http.get('/api/v1/agent/templates', () => {
    return HttpResponse.json(MOCK_TEMPLATES);
  }),

  // ── V8.2: 同步接口（保留兼容）──
  http.post('/api/v1/agent/analyze', async ({ request }) => {
    const body = await request.json() as { query: string; template?: string };
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

  // ── V8.2: SSE 流式接口 ──
  http.post('/api/v1/agent/analyze/stream', async ({ request }) => {
    const body = await request.json() as { query: string; template?: string };
    if (!body.query || body.query.trim().length === 0) {
      return HttpResponse.json(
        { detail: 'query 不能为空' },
        { status: 422 },
      );
    }

    // 构建 SSE 事件流
    const events = [
      JSON.stringify({ type: 'plan_start', task_count: 3, tasks: [
        { id: '1', type: 'data_query', desc: '查询财务数据' },
        { id: '2', type: 'calculate', desc: '计算盈利指标' },
        { id: '3', type: 'analyze', desc: '综合分析生成结论' },
      ], message: '已规划 3 个子任务' }),
      JSON.stringify({ type: 'task_start', task_id: '1', description: '查询财务数据', task_idx: 1, total: 3 }),
      JSON.stringify({ type: 'task_complete', task_id: '1', success: true, summary: '营收1709.90亿元，净利润862.28亿元' }),
      JSON.stringify({ type: 'task_start', task_id: '2', description: '计算盈利指标', task_idx: 2, total: 3 }),
      JSON.stringify({ type: 'task_complete', task_id: '2', success: true, summary: '毛利率92.01%，净利率50.56%，ROE36.99%' }),
      JSON.stringify({ type: 'task_start', task_id: '3', description: '综合分析生成结论', task_idx: 3, total: 3 }),
      JSON.stringify({ type: 'task_complete', task_id: '3', success: true, summary: '分析结论已生成' }),
      JSON.stringify({ type: 'done', report: `## ${body.query}分析报告\n\n分析完成。`, charts: [], chart_options: [], task_count: 3, processing_time: 2.5, message: '分析完成，耗时 2.5 秒' }),
    ];

    const sseText = events.map((e) => `data: ${e}\n\n`).join('');

    return new HttpResponse(sseText, {
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }),

  // ── RAG API ──
  http.get('/api/v1/rag/documents', () => {
    return HttpResponse.json({ documents: MOCK_DOCUMENTS, total: MOCK_DOCUMENTS.length });
  }),

  http.post('/api/v1/rag/upload', async () => {
    return HttpResponse.json({
      filename: '测试文档.pdf',
      file_size: 1024000,
      chunk_count: 42,
      message: '上传成功',
    });
  }),

  http.post('/api/v1/rag/chat', async ({ request }) => {
    const body = await request.json() as { query: string };
    if (!body.query || body.query.trim().length === 0) {
      return HttpResponse.json(
        { detail: 'query 不能为空' },
        { status: 422 },
      );
    }
    return HttpResponse.json({
      ...MOCK_CHAT_RESPONSE,
      answer: `关于"${body.query}"的分析：${MOCK_CHAT_RESPONSE.answer}`,
    });
  }),
];
