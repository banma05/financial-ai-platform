import { setupServer } from 'msw/node';
import { handlers } from './handlers';

/** MSW 测试服务器 — 在 vitest 环境中拦截网络请求 */
export const server = setupServer(...handlers);
