import { useState, useRef, useCallback } from 'react';

/** SSE 事件中的任务信息 */
interface StreamTask {
  id: string;
  type: string;
  desc: string;
}

/** 流式分析进度状态 */
export interface AnalysisProgress {
  phase: 'idle' | 'planning' | 'executing' | 'done' | 'error';
  /** 已完成任务数 */
  completed: number;
  /** 总任务数 */
  total: number;
  /** 当前任务描述 */
  currentTask: string;
  /** 任务详情列表 */
  tasks: Array<{ id: string; desc: string; success: boolean; summary?: string }>;
  /** 最终报告 */
  report: string | null;
  /** 图表 base64 数组 */
  charts: string[];
  /** 总耗时 */
  processingTime: number | null;
  /** 错误信息 */
  error: string | null;
}

const INITIAL_PROGRESS: AnalysisProgress = {
  phase: 'idle',
  completed: 0,
  total: 0,
  currentTask: '',
  tasks: [],
  report: null,
  charts: [],
  processingTime: null,
  error: null,
};

/**
 * useAnalysisStream — POST SSE 流式分析 Hook
 *
 * 后端 /api/v1/agent/analyze/stream 返回 SSE 事件流：
 *   plan_start → task_start → task_complete → chart → done
 *
 * 用法：
 *   const { progress, startStream, abort } = useAnalysisStream();
 *   await startStream({ query: '茅台2024年盈利能力', template: 'profitability' });
 */
export function useAnalysisStream() {
  const [progress, setProgress] = useState<AnalysisProgress>(INITIAL_PROGRESS);
  const abortRef = useRef<AbortController | null>(null);

  const startStream = useCallback(async (params: {
    query: string;
    template?: string;
    session_id?: string;
  }) => {
    // 重置状态
    const controller = new AbortController();
    abortRef.current = controller;
    setProgress({ ...INITIAL_PROGRESS, phase: 'planning' });

    try {
      const response = await fetch('/api/v1/agent/analyze/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(import.meta.env.VITE_API_KEY ? { 'X-API-Key': import.meta.env.VITE_API_KEY } : {}),
        },
        body: JSON.stringify({
          query: params.query,
          template: params.template || null,
          session_id: params.session_id || `preset-${Date.now()}`,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`服务器错误 (${response.status})`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('浏览器不支持流式响应');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件（以 \n\n 分隔）
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || ''; // 最后一个可能不完整，保留到下次

        for (const part of parts) {
          // 提取 data: 行
          const dataLines = part
            .split('\n')
            .filter((line) => line.startsWith('data: '))
            .map((line) => line.slice(6));

          for (const dataStr of dataLines) {
            try {
              const event = JSON.parse(dataStr);
              handleSSEEvent(event);
            } catch {
              // 跳过非 JSON 数据
            }
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        setProgress((p) => ({ ...p, phase: 'idle' }));
        return;
      }
      setProgress((p) => ({
        ...p,
        phase: 'error',
        error: (err as Error).message || '流式分析失败',
      }));
    }
  }, []);

  /** 处理单个 SSE 事件，更新进度状态 */
  const handleSSEEvent = useCallback((event: Record<string, unknown>) => {
    const type = event['type'] as string;

    switch (type) {
      case 'plan_start':
        setProgress((p) => ({
          ...p,
          phase: 'executing',
          total: (event['task_count'] as number) || 0,
          tasks: ((event['tasks'] as StreamTask[]) || []).map((t) => ({
            id: t.id,
            desc: t.desc,
            success: false,
          })),
          currentTask: (event['message'] as string) || '正在规划分析步骤...',
        }));
        break;

      case 'task_start':
        setProgress((p) => ({
          ...p,
          currentTask: (event['description'] as string) || (event['message'] as string) || '',
        }));
        break;

      case 'task_complete':
        setProgress((p) => {
          const taskId = event['task_id'] as string;
          const success = (event['success'] as boolean) || false;
          const summary = event['summary'] as string | undefined;
          const newTasks = p.tasks.map((t) =>
            t.id === taskId ? { ...t, success, summary } : t,
          );
          const completed = newTasks.filter((t) => t.success).length;
          return {
            ...p,
            completed,
            tasks: newTasks,
            currentTask: (event['message'] as string) || '',
          };
        });
        break;

      case 'chart':
        setProgress((p) => ({
          ...p,
          charts: [...p.charts, (event['chart_base64'] as string) || ''],
        }));
        break;

      case 'report_start':
        setProgress((p) => ({ ...p, phase: 'done', currentTask: '正在生成报告...' }));
        break;

      case 'done':
        setProgress((p) => ({
          ...p,
          phase: 'done',
          report: (event['report'] as string) || '',
          charts: (event['charts'] as string[]) || p.charts,
          processingTime: (event['processing_time'] as number) || 0,
        }));
        break;

      case 'error':
        setProgress((p) => ({
          ...p,
          phase: 'error',
          error: (event['message'] as string) || '分析失败',
        }));
        break;

      case 'clarification':
        setProgress((p) => ({
          ...p,
          phase: 'done',
          report: `### ⚠️ 需要更多信息\n\n${event['question'] || ''}\n\n请补充信息后重试。`,
        }));
        break;
    }
  }, []);

  /** 取消分析 */
  const abort = useCallback(() => {
    abortRef.current?.abort();
    setProgress(INITIAL_PROGRESS);
  }, []);

  return { progress, startStream, abort };
}
