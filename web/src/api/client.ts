import axios from 'axios';

/** 预配置的 axios 实例，baseURL 通过 Vite proxy 转发到后端 */
export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 120000, // Agent 分析可能较慢
  headers: { 'Content-Type': 'application/json' },
});

// 响应拦截器：统一提取 data（类型擦除后用，调用处自行 cast）
apiClient.interceptors.response.use(
  (res) => res.data,
  (error) => {
    const message = error.response?.data?.detail || error.message || '请求失败';
    return Promise.reject(new Error(message));
  },
);
