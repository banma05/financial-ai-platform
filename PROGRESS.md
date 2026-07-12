# 智能财务分析平台 — 项目进度

> 📅 最后更新：2026-07-12
> 🎯 当前版本：**V8.1** — 质量打磨进行中
> 🏗️ 状态：阶段A ✅ → 阶段B ✅ → 阶段C ✅ → D-A安全防线 ✅ → D-B并发稳定 ✅ → D-C架构清理 ⏳

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

### D-C 架构清理 ⏳ (D6+D9+D13)

---
---
## 已知限制 (诚实)

- 口语化表达未支持 ("赚了多少钱")
- 年份默认去年 (可能不是最新年报)
- 三家跨公司键名匹配残差
- RAG/Agent 评测待跑 (阶段C)
