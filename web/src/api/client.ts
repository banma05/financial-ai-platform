import axios from 'axios';

/** 预配置的 axios 实例，baseURL 通过 Vite proxy 转发到后端 */
const _client = axios.create({
  baseURL: '/api/v1',
  timeout: 120000, // Agent 分析可能较慢
  headers: {
    'Content-Type': 'application/json',
    // V8.1 D4: 开发模式下从环境变量读取 API Key
    ...(import.meta.env['VITE_API_KEY'] ? { 'X-API-Key': import.meta.env['VITE_API_KEY'] } : {}),
  },
});

// 响应拦截器：统一错误处理
_client.interceptors.response.use(
  (res) => res,
  (error) => {
    const message = error.response?.data?.detail || error.message || '请求失败';
    return Promise.reject(new Error(message));
  },
);

/** V8.1 D8: 类型安全的 API 客户端，消除 as unknown as */
export const api = {
  async get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
    const res = await _client.get<T>(url, { params });
    return res.data;
  },
  async post<T>(url: string, body?: unknown, config?: Record<string, unknown>): Promise<T> {
    const res = await _client.post<T>(url, body, config);
    return res.data;
  },
};

/** @deprecated 旧版 apiClient，逐步迁移到 api.get<T>() / api.post<T>() */
export const apiClient = _client;
