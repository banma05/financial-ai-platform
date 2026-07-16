# 智能财务分析平台 — 项目进度

> 📅 最后更新：2026-07-16
> 🎯 当前版本：**V8.2** 🔴🟡 进行中
> 🏗️ 状态：V8.2 核心项完成 → 剩余 Docker验证 + E2E测试

---

## V8.2 本轮交付 (2026-07-16)

| 维度 | 改动 | 效果 |
|------|------|------|
| 🔴 死机修复 | 移除 graph.py ThreadPoolExecutor 嵌套 | 消除线程嵌套+锁竞争风险 |
| 🔴 SSE 流式 | 前端 useAnalysisStream + PresetAnalysis 改造 | **告别16秒白屏**，实时进度反馈 |
| 🔴 熔断器 | AKShare 5个入口接入熔断器(3次→OPEN,60s) | 外部故障不拖垮系统 |
| 🟡 代码规范 | embedder.py 缩进修复 | 参数对齐 |

**验证：** 后端 385/385 ✅ + 前端 14/14 ✅ + TypeScript 0 错误

### V8.2 剩余项

| # | 事项 | 状态 |
|:--:|------|:--:|
| 1 | Docker 一键部署验证 | ⬜ 未验证 |
| 2 | 前端 E2E 测试 | ⬜ 未实现 |
| 3 | ChromaDB 熔断器 | ⬜ 低优先级（本地DB） |

### V8.2 已完成项

| # | 事项 | 状态 |
|:--:|------|:--:|
| 1 | 熔断器接入 LLM | ✅ |
| 2 | Agent Planner prompt 优化 | ✅ |
| 3 | RAG 幻觉 Prompt 强化 + 后处理检测 | ✅ |
| 4 | Agent 超时策略 (15s/45s/5任务) | ✅ |
| 5 | CI 测试扩展 (295→385) | ✅ |
| 6 | Agent Reporter 数值校验 | ✅ |
| 7 | 口语化查询映射 | ✅ |
| 8 | **SSE 流式消费** | ✅ **本轮新增** |
| 9 | **AKShare 熔断器** | ✅ **本轮新增** |
| 10 | **死机风险修复** | ✅ **本轮新增** |

---

## V8.0 评测基线 (2026-07-09)

| 维度 | V7.0 | V8.0 | 备注 |
|------|:--:|:--:|------|
| SQL 覆盖率 | — | **100%** (24/24) | 单/多公司+多年份 |
| SQL 准确率 | ~60% | **83.3%** (20/24) | 残差来自AKShare精度 |
| SQL 平均延迟 | 20-80s | **1.4ms** | 零LLM |
| 多公司查询 | ❌ | ✅ | 茅台vs五粮液等 |
| 规则提取 | ❌ (LLM) | **56指标,100%准确** | 零LLM,表格→SQL |
| Agent 任务类型 | 3种 | **4种** | +rag_context(原文解读) |
| 代码量 | 16,041 | 13,521 | -2,520行 |
| CI 测试 | 10失败 | ✅ 通过 | 162/162 |

---

## 三阶段实施

| 阶段 | 内容 | 状态 |
|------|------|:--:|
| **A** 引擎补完 | 规则提取 + RAG任务 + 上传闭环 | ✅ |
| **B** 体验优化 | React前端 + 预设标签 + 报告展示 | ✅ |
| **C** 质量防线 | Agent/RAG评测 + 回归验证 | ✅ |

---

## 阶段A 交付 (2026-07-09)

| 组件 | 功能 |
|------|------|
| 规则提取引擎 `rag/table_extractor.py` | 表格→行标签匹配→SQL, 零LLM, 56指标 |
| RAG上下文工具 `agent/tools/rag_context.py` | 检索原文→LLM提炼→报告引用 |
| 上传集成 `api/rag.py` | 上传自动触发规则提取+RAG索引 |

## 阶段B 交付 (2026-07-10)

| 组件 | 功能 |
|------|------|
| React 前端骨架 `web/` | Vite 8 + React 19 + TS 6 + TailwindCSS v4 |
| 预设分析页 | 5家公司标签 + 3模板 + 推荐问题 + 一键分析 |
| 文档上传页 | PDF拖拽上传 + 文档列表 + RAG问答 + 来源引用 |
| 报告展示页 | react-markdown + ECharts + 导出PDF/文本 |
| 状态管理 | Zustand 跨页面共享分析结果 |
| 测试体系 | 14测试全过 (Vitest + Testing Library + MSW) |

### 前端技术栈

React 19 · Vite 8 · TailwindCSS v4 · ECharts 6 · React Router v7 · Zustand v5 · axios · Vitest 4

---

## 项目结构 (V8.0)

```
financial-ai-platform/
├── backend/                  # FastAPI 后端 (:8001)
│   ├── agent/                # LangGraph Agent (Planner→Executor→Reporter)
│   ├── rag/                  # RAG引擎 (BM25+语义+ChromaDB)
│   ├── mcp/                  # MCP 6工具
│   ├── db/                   # SQLite 业务库
│   ├── api/                  # FastAPI 路由
│   ├── models/               # Pydantic 模型
│   └── tests/                # 385单元测试
├── web/                      # React 前端 (:5173) [NEW]
│   ├── src/pages/            # 三页面 + 组件
│   ├── src/stores/           # Zustand 状态管理
│   └── src/__tests__/        # 14前端测试
├── evaluation/               # 评测脚本+数据集+报告
├── data/                     # 文档+向量库+模型
├── docs/                     # 设计文档
└── scripts/                  # 运维脚本
```

---

## 启动

```bash
# 后端 :8001
source ../.venv/Scripts/activate
python backend/main.py

# 前端 :5173 (开发模式，自动代理 /api → :8001)
cd web && npx vite
```

## 测试

```bash
python scripts/run_tests.py     # 后端 385测试
cd web && npx vitest run        # 前端 14测试
```

## 评测

```bash
python evaluation/v8_bench.py --layer sql     # SQL 20题
python evaluation/v8_bench.py --layer agent   # Agent 15题
python evaluation/v8_bench.py --layer rag     # RAG 15题
```

---

## V8.1 质量打磨 (2026-07-12)

### D-A 安全防线 ✅

| # | 修复 | 文件 | 说明 |
|---|------|------|------|
| D1 | OpenAI 超时 | `model_router.py` | `timeout=60s`，`request_timeout=60s` |
| D2 | CORS :5173 | `main.py` | 默认源新增 `http://localhost:5173` |
| D4 | 开发模式鉴权 | `auth.py` | API_KEY 为空时自动生成 `dev-*` 密钥 |
| D12 | MIME 收紧 | `api/rag.py` | 移除 octet-stream 直接放行 |

> 测试：385/385 ✅ | Auth：17/17 ✅

### D-B 并发稳定 ✅

| # | 修复 | 文件 | 说明 |
|---|------|------|------|
| D3 | async 阻塞 | `api/rag.py` | `asyncio.to_thread` 卸载同步 LLM/检索调用 |
| D5 | 会话 TTL | `api/rag.py` | TTL 1h + LRU 1000 + 线程安全清理 |
| D14 | BM25 内存 | `hybrid_search.py` | 仅缓存 ID+元数据，正文按需查 ChromaDB |

> 测试：385/385 ✅ | HybridSearch：35/35 ✅

### D-C 架构清理 ✅

| # | 修复 | 文件 | 说明 |
|---|------|------|------|
| D6 | ORM 注入 | `api/rag.py` | 路由函数使用 `Depends(get_db)` 依赖注入 |
| D9 | 会话统一 | `api/rag.py` | 统一为 `redis_client.SessionStore`，消除三套竞争 |
| D13 | eval 替换 | `financial_query.py` | AST 白名单安全求值器，仅允许 + - * / |

> 测试：385/385 ✅ | 核心：105/105 ✅

### D-D 质量收尾 ✅

| # | 修复 | 文件 | 说明 |
|---|------|------|------|
| D7 | ECharts 死代码 | `ReportView.tsx` | 移除 ~120KB 无用依赖 |
| D8 | 类型断言 | 3 文件 | 消除 5 处 `as unknown as`，新增 `api.get<T>` |
| D15 | 无用包 | `requirements.txt` | 移除 pydantic-settings, markdown |
| D16 | tslib | `package.json` | esbuild 不需要 tslib |
| D17 | 公司列表 | PresetAnalysis + main.py | 新增 `/api/v1/companies`，前端动态获取 |
| D18 | 硬编码年份 | `PresetAnalysis.tsx` | 改为 `new Date().getFullYear()` |
| D19 | 配置硬编码 | main.py + vite.config.ts | 端口/代理改用环境变量 |
| D20 | CI 补全 | `test.yml` | 新增 frontend-test job |
| D21 | .gitignore | `.gitignore` | 添加 `evaluation/reports/` |

> 前端：14/14 ✅ | TypeScript：零错误 | CI：双 Job

---
## V8.1 总结

| 阶段 | 项目数 | 测试 |
|------|:--:|:--:|
| D-A 安全防线 | 4 | 385/385 |
| D-B 并发稳定 | 3 | 385/385 |
| D-C 架构清理 | 3 | 385/385 |
| D-D 质量收尾 | 11 | 14/14 前端 + 385/385 后端 |
| **合计** | **21/21** | **全部通过** |

---
---
## 已知限制 (诚实)

- 口语化表达未支持 ("赚了多少钱")
- 年份默认去年 (可能不是最新年报)
- 三家跨公司键名匹配残差
- RAG/Agent 评测待跑 (阶段C)
