# 智能财务分析平台 — 架构文档

> 当前版本 V9.2 | 架构说明

---

## 一、整体架构

```
用户 (React SPA)
    │  SSE 流式
    ▼
FastAPI (:8001)
    │
    ├─ /api/v1/agent/*     ─── Agent 分析引擎（核心）
    ├─ /api/v1/rag/*       ─── RAG 知识库检索
    └─ /api/v1/admin/*     ─── 管理/监控
    │
    ├─ Redis (会话+限流)
    ├─ SQLite (财务数据库, 20家公司)
    └─ ChromaDB (向量库, ~5000 chunks)
```

**Agent 核心流水线：**

```
Planner(LLM) ──→ Executor(线性) ──→ Reporter(LLM)
    │                  │                   │
    │           ┌──────┼──────┐            │
    │           ▼      ▼      ▼            │
    │        SQL查   RAG辅助  公式计算     │
    │       (毫秒级) (语义)  (零LLM)      │
    │           │      │      │            │
    └───────────┴──────┴──────┴────────────┘
              结构化数据 + 语义解读 → 报告+图表
```

---

## 二、四个核心设计决策

### 1. 为什么 LangGraph 而不是自研 DAG？

**V7.0 踩过的坑**：自研了一个 DAG 执行引擎，支持并行任务 + 依赖管理。但遇到三个致命问题：
- 条件路由（追问 vs 执行）需要大量 if-else
- 流式输出需要手动管理 generator 生命周期
- 错误恢复和重试需要自己实现状态机

**换 LangGraph 后**：三节点 StateGraph（Planner → Executor → Reporter），
50 行代码替代 350 行自研 DAG。状态管理、流式、错误恢复全部内置。

### 2. 为什么 SQL 优先而不是 RAG 优先？

财务分析的核心需求是**精确数值**（毛利率=91.93%，不是"约92%"）。

- **SQL 路径**：毫秒级，精确到小数点后两位，零 LLM 调用
- **RAG 路径**：秒级，文字解读和原因分析（"为什么毛利率下降？"），补充 SQL 无法回答的定性问题

两条路径互补：SQL 保证数据精度，RAG 提供语义深度。整体延迟控制在合理范围。

### 3. 为什么自己写 DI 容器？

项目有 ~15 个应用级单例（Embedding 模型、ChromaDB、CrossEncoder 等），
需要线程安全的惰性初始化 + 测试 mock 替换。

60 行 `threading.RLock` + 惰性工厂 = 解决全部需求。
引入 3000 行的 `dependency-injector` 是过度设计。

> FastAPI `Depends` 是请求级 DI，`Container` 是应用级 DI，两者互补而非替代。

### 4. 为什么 ChromaDB 而不是 Pinecone/Weaviate？

- **免费** — Pinecone 最低 $70/月，ChromaDB 零成本
- **本地部署** — 财务数据不出本地，合规友好
- **嵌入式** — 不需要独立服务进程，一键启动
- **HNSW 索引** — 对 ~10K chunks 规模，性能足够（毫秒级查询）

---

## 三、架构原则（V9.1 演进）

经历多轮迭代后，沉淀为四条必须强制执行的架构约束：

| 约束 | 目的 | 落地 |
|:---|:---|:---|
| 信任边界 | 抵御 Prompt 注入、隔离错误信息 | `InputSanitizer` + XML 硬隔离 |
| 依赖方向 | 统一数据访问，杜绝散落的 DB 连接 | `Repository` 层 + DI Container |
| 并发模型 | 线程安全、单例生命周期可控 | `Container` + RLock |
| 配置单一可信源 | 公司注册表等配置只维护一处 | `config.py` 统一入口 |

---

## 四、技术栈

| 层 | 技术 | 选型理由 |
|:---|:---|:---|
| 后端框架 | FastAPI | 异步原生、自动 OpenAPI |
| Agent 编排 | LangGraph | StateGraph 三节点 |
| LLM | DeepSeek v4-pro/v4-flash | 性价比、中文能力强 |
| Embedding | BAAI/bge-base-zh-v1.5 | 768 维、本地免费 |
| Reranker | BAAI/bge-reranker-v2-m3 | Cross-Encoder 精排 |
| 向量库 | ChromaDB | 嵌入式、零成本 |
| 数据库 | SQLite → MySQL | 环境变量一键切换 |
| 前端 | React 19 + Zustand + ECharts | SPA + 状态管理 + 图表 |
| 分词 | jieba | BM25 中文分词 |

---

## 五、已知限制与未来方向

- **数据规模**：当前 20 家 A 股公司 + 14 份年报，扩展到 5000 家需迁移 PostgreSQL
- **LLM 延迟**：端到端平均约 25s（DeepSeek API 为主），未来可换本地模型或模板缓存
- **多轮对话**：规划中，需要会话上下文管理器
- **Agent 验证节点**：Executor 后加 verify_node，数据不足时回退重规划
