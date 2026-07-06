
# 项目进度存档

> 📅 最后更新：2026-07-06
> 🎯 目标：智能财务分析平台（三模块：知识库 + Agent + MCP）
> 📌 当前阶段：**阶段五 ✅ + P1 清零 → 阶段六待启动**
> 🗺️ 完整五阶段路线图见下文「版本路线 V3.0」

---

## 五阶段工程化路线图（V3.0）

| 阶段 | 内容 | 状态 | 预计产出 |
|------|------|:----:|------|
| **阶段一** | 修复6个关键Bug + 清理死代码 | ✅ 完成 (7/4) | 稳定Agent基础 |
| **阶段二** | 智能依赖注入 + 重试机制 + 结构化日志 | ✅ 完成 (7/5) | Agent工程化升级 |
| **阶段三** | MCP模块从零开发（6+工具）+ AKShare | ✅ 完成 (7/5) | 外部数据源接入 |
| **阶段四** | Docker + Redis + CI/CD + 集成测试 | ✅ 完成 (7/5) | 生产级工程补齐 |
| **阶段五** | 三模块联动整合 + 统一评测 | ⏳ 进行中 (7/6) | 端到端数据流打通 |
| **阶段六** | 六维审计优化（上下文/成本/人机协同） | ⏳ 待启动 | Agent 含金量提升 |

### 核心架构决策（2026-07-04）
- ✅ **采用 LangGraph StateGraph**：业界标准 Agent 编排框架，StateGraph 做顶层编排 + ThreadPoolExecutor 做层内并行
- ✅ **LLM 统一调用**：全部走 `chat()`，删除 `get_langchain_llm()`
- ✅ **MCP 先内置后独立**：阶段三复用 ToolRegistry，阶段四 Docker 化拆独立进程
- ✅ **高并发路线**：短期 Lock+TTL+重试 → 中期 Redis+MySQL → 长期 Milvus+K8s

---

## 项目架构总览

### 实际目录结构

```
financial-ai-platform/
├── backend/
│   ├── rag/              ← 模块一：知识库 RAG（检索+索引+评估）
│   │   ├── loader.py          文档加载（PDF/Word/MD/TXT + 表格提取）
│   │   ├── semantic_splitter.py  语义动态切分
│   │   ├── embedder.py        BGE 向量化
│   │   ├── vector_store.py    ChromaDB 管理
│   │   ├── hybrid_search.py   混合检索（BM25+语义→RRF→LambdaMART）
│   │   ├── query_processor.py Query 理解（术语展开+LLM扩写+校验）
│   │   ├── entity_router.py   实体识别+文档路由
│   │   ├── jieba_tokenizer.py 中文分词+138财务词典
│   │   ├── retriever.py       完整 RAG 问答入口（prompt构建+溯源）
│   │   ├── evaluator.py       评测库（被 API/retriever/experiments 使用）
│   │   ├── model_router.py    LLM 统一调用（chat/chat_stream/flash-pro分层）
│   │   ├── experiments.py     参数实验
│   │   └── quick_tune.py      快速调优
│   │
│   ├── agent/             ← 模块二：数据分析 Agent（LangGraph 编排）
│   │   ├── api.py              公共 API 显式导出（V5.1 新增）
│   │   ├── graph.py            LangGraph StateGraph 顶层编排
│   │   ├── planner.py          任务拆解 + 5模板
│   │   ├── executor.py         ToolRegistry + 依赖注入
│   │   ├── reporter.py         报告生成（5章节Markdown）
│   │   ├── schemas.py          内部数据模型（AnalysisTask/TaskResult 等）
│   │   └── tools/
│   │       ├── data_query.py    RAG检索→结构化提取
│   │       ├── financial_calc.py 19财务公式（7大类）
│   │       ├── chart.py         5种图表（line/bar/pie/radar/dual_axis）
│   │       └── param_injection.py  三层回退依赖注入
│   │
│   ├── utils/             ← 公共工具层
│   │   ├── retry.py            tenacity重试 + CircuitBreaker
│   │   └── logger.py           结构化日志（trace_id + JSON + 轮转）
│   │
│   ├── api/               ← FastAPI 路由层
│   │   ├── rag.py              RAG 问答 API（上传/对话/评测）
│   │   └── agent.py            Agent 分析 API（同步+SSE流式）
│   │
│   ├── middleware/         ← 中间件层
│   │   └── auth.py             X-API-Key 鉴权 + 滑动窗口限流
│   │
│   ├── models/            ← Pydantic 数据模型（API 契约）
│   │   └── schemas.py          AgentRequest/AgentResponse/TemplateInfo 等
│   │
│   ├── db/                ← 数据库（预留，阶段四启用）
│   ├── tests/             ← 单元测试（130+ 用例）
│   ├── config.py          ← 全局配置
│   └── main.py            ← FastAPI 入口
│
├── evaluation/            ← 评测脚本 + 数据集 + 报告
│   ├── rag/quick_eval.py       RAG 50题双轨评测
│   ├── agent/bench_agent.py    Agent 子任务拆解评测
│   ├── bench_speed.py          检索速度基准
│   ├── data/                   评测数据集
│   │   ├── rag_questions.json
│   │   └── agent_questions.json
│   └── reports/                评测报告输出
│
├── scripts/               ← 运维脚本
│   ├── run_tests.py            测试运行器
│   └── rebuild_index.py        一键重建向量索引
│
├── frontend/              ← Streamlit 前端
│   └── app.py
│
├── data/                  ← 运行时数据
│   ├── documents/              原始文档
│   ├── chroma_db/              ChromaDB 持久化
│   └── models/                 本地 Embedding 模型
│
├── logs/                  ← 应用日志（trace_id + JSON 按天轮转）
├── docs/                  ← 文档（BRD/架构图）
├── requirements.txt
├── PROGRESS.md
└── README.md
```

### 按 RAG 标准能力域对照

> 参照业界 RAG 七领域框架，逐项标注当前覆盖度和已知缺口。

| 能力域 | 关键技能 | 当前实现 | 覆盖度 | 缺口 |
|--------|---------|---------|:------:|------|
| **retrieval** 检索 | Query理解/改写/混合检索/重排 | query_processor + hybrid_search + LambdaMART | 🟢 85% | 缺意图分类、HyDE、多轮改写 |
| **indexing** 索引 | 文档加载/分块/向量化/索引构建 | loader + semantic_splitter + embedder + ChromaDB | 🟢 85% | **缺 metadata 独立管理层** |
| **knowledge-base** 知识库 | 数据源/语料管理/更新同步/质量/版本 | corpus_manager + 前端面板 | 🟡 60% | ✅增量 ✅质量检查 ✅语料UI ✅版本快照；缺自动回滚 |
| **generation** 生成 | Prompt模板/上下文组装/LLM生成/引用/幻觉控制 | retriever(结构化引用) + reporter | 🟡 70% | ✅[^N]脚注式引用；缺幻觉检测 |
| **evaluation** 评估 | 检索评估/生成评估/端到端/指标/基准 | evaluator(50题+R@k/MRR/NDCG+LLM) | 🟢 85% | 缺生成质量专项评估( faithfulness / relevancy 完整版) |
| **observability** 可观测 | 日志/追踪/监控/告警/仪表盘 | logger(trace_id) + monitor(追踪+告警) + 前端面板 | 🟢 80% | ✅Dashboard ✅告警 ✅P50/P95/P99延迟；缺外部门槛告警 |
| **integration** 集成部署 | API/Agent/工作流/工具化/部署 | FastAPI+Streamlit+LangGraph | 🟡 65% | 缺 Docker/CI/CD（阶段四）；MCP 已完成 |

> **结论**：我们的 RAG 在 **检索** 和 **索引** 两个核心域已达到生产级，但 **知识库管理** 和 **可观测性** 是最大短板。这两个域不需要复杂算法，主要是工程规范化——适合在阶段四统一补齐。

### 模块完成度总览

| 模块 | 定位 | 状态 | 完善度 | 核心基线 |
|------|------|:----:|:------:|----------|
| **rag/** | 知识库 RAG（检索+索引+评估） | ✅ | 🟢 85% | SEM-R@5=95.2%, MRR=89.5%, GPU加速6.7x |
| **agent/** | 数据分析 Agent（编排+工具+报告） | ✅ | 🟢 85% | LangGraph+5模板+19公式+注入+重试+trace_id+评测基线77.4% |
| **utils/** | 公共工具层（重试+日志） | ✅ | 🟢 90% | tenacity重试+CircuitBreaker+trace_id+JSON轮转 |
| **api/** | FastAPI 路由 | ✅ | 🟢 85% | 7端点+SSE流式+鉴权限流 |
| **middleware/** | 鉴权限流 | ✅ | 🟢 85% | X-API-Key+滑动窗口(30/min通用,10/min Chat) |
| **tests/** | 单元测试 | ✅ | 🟢 85% | 130用例，agent 96 + rag 196 = 覆盖核心路径 |
| **MCP** | 外部数据源接入 | ⏳ | — | 阶段三开发（6+工具） |
| **工程化** | Docker/Redis/CI/CD | ⏳ | — | 阶段四统一补齐 |

---

## 模块一：知识库 RAG ✅

### 当前状态

| 组件 | 完善度 | 说明 |
|------|:------:|------|
| 文档加载 | 🟢 90% | PDF/Word/MD/TXT + 表格结构化提取(547表/3年报) |
| 语义切分 | 🟢 90% | mean-1std 动态切分，chunks 1964（-32%碎片），大表格注入 |
| 向量化 | 🟢 90% | bge-base-zh-v1.5 768维，本地免费 |
| 向量存储 | 🟢 90% | ChromaDB HNSW 持久化 + BM25 索引缓存(每次查询省7s) |
| Query 处理 | 🟢 85% | 术语展开 + LLM扩写 + 余弦校验 |
| 混合检索 | 🟢 90% | BM25+语义 → RRF(k=60) → LambdaMART(默认) |
| Entity Routing | 🟡 60% | 公司实体识别+文档过滤，保留为可选能力 |
| 检索+问答 | 🟢 85% | deepseek-v4-pro，引用溯源，流式SSE |
| API 安全 | 🟢 85% | X-API-Key 鉴权 + 滑动窗口限流(通用30/min，Chat10/min) |
| 评测体系 | 🟢 95% | 50题双轨(关键词+语义) + R@k/MRR/NDCG + 数字归一化 |
| 单元测试 | 🟢 85% | 196用例覆盖7组件（含鉴权/表格/测试集验证） |
| 参数实验 | 🟢 90% | chunk/overlap/阈值调优，索引精简71% |
| FastAPI 后端 | 🟢 90% | 5接口+流式SSE+鉴权限流，缺Docker化 |
| Streamlit 前端 | 🟢 80% | 流式输出+对话历史+三模块导航，缺图表展示 |
| **GPU 加速** | 🟢 90% | CrossEncoder(RTX4060) GPU推理，检索提速6.7x |

### 评测基线

| 场景 | KW-R@5 | SEM-R@5 | MRR | 说明 |
|------|:--------:|:--------:|:----:|------|
| 单文档（比亚迪）| 91.2% | — | 85.8% | ~800 chunks |
| 多文档-v1（3年报,mean-0.5std）| **87.3%** | — | **90.8%** | 2882 chunks，33题 |
| 多文档-v2（3年报,mean-1std）| **70.4%** | **95.2%** | **89.5%** | 1382 chunks，50题，7/4 |
| GPU加速 | — | — | — | 单题1.5s (CPU版10s)，7/4 |

> **7/4 重要发现**：关键词评测(KW-R@5=70.4%)严重低估真实检索质量。语义评测(SEM-R@5=95.2%)证明检索在语义层面非常准确，25pp的差距源于 expected_keywords 标注不全（如"资本负债率" vs chunk中的"资产负债率"）。

### 待办

- [x] ~~API 鉴权 + 限流~~ ✅ (2026-07-01)
- [x] ~~PDF 表格结构化提取验收~~ ✅ (2026-07-01)
- [x] ~~测试集从33题扩充到50题~~ ✅ (2026-07-01)
- [x] ~~多轮对话记忆~~ ✅ (2026-07-01)
- [x] ~~补充边界异常+脏数据测试~~ ✅ (2026-07-01, +10题)
- [x] ~~响应时间基线~~ ✅ (2026-07-01, bench_speed.py)

---


## 模块二：数据分析 Agent ✅ V3.0（阶段一+二完成）

### 当前状态

| 组件 | 完善度 | 说明 |
|------|:------:|------|
| Planner（任务拆解） | 🟢 85% | LLM 拆解(flash/pro) + 5模板 + 追问澄清 |
| Executor（工具执行） | 🟢 90% | ToolRegistry + ParamInjector三层注入 + DAG层内并行 |
| DataQuery 工具 | 🟡 65% | 封装 RAG + LLM 结构提取 + flash→pro自动重试 |
| FinancialCalc 工具 | 🟢 90% | 19个内置公式，7大类，纯 Python 零依赖 |
| Chart 工具 | 🟢 80% | 5种图表（line/bar/pie/radar/dual_axis），base64 嵌入 |
| Reporter（报告生成） | 🟢 80% | Markdown 五章节报告 + LLM 洞察生成 |
| API 路由 | 🟢 85% | 4端点（同步+SSE流式+模板+公式），鉴权限流继承 |
| 前端 UI | 🟢 80% | SSE 流式进度 + 报告渲染 + 图表展示 + 历史记录 |
| 工程化（阶段二） | 🟢 90% | tenacity重试+CircuitBreaker+trace_id+JSON日志轮转 |

### 核心交付

| 能力 | 说明 | 状态 |
|------|------|:----:|
| NL 驱动数据查询 | 自然语言→RAG检索→结构化提取 | ✅ |
| 自动分析报告 | 数据→图表→结论→建议 五章节报告 | ✅ |
| 可视化图表 | 5种图表类型，中文字体自动适配 | ✅ |
| 财务公式库 | 19个公式（盈利/偿债/营运/成长/估值/现金流/杜邦） | ✅ |
| 分析模板库 | 盈利能力/杜邦/成长/现金流/风险扫描 5 模板 | ✅ |
| 追问澄清 | 需求模糊时 Planner 返回追问 | ✅ |
| DAG 多步推理 | LangGraph StateGraph 编排 + 拓扑排序层内并行 | ✅ |
| 智能依赖注入 | 三层回退（精确→编辑距离→LLM语义），命中率可统计 | ✅ |
| 错误恢复 | chat() @retry 退避 + 429自动延长 + CircuitBreaker | ✅ |
| 全链路追踪 | trace_id 贯穿 planner→executor→reporter + 计时 | ✅ |

### 验收指标

| 指标 | 目标 | 当前 
|------|:----:|:----:|
| 子任务拆解准确率 | ≥85% | 待评测（76.9%，阶段三后重测） |
| 指标计算准确率 | ≥98% | ✅ 105测试通过（公式40+注入41+Planner15+重试19+日志15=130） |
| 端到端分析耗时 | ≤30s | 待基准测试 |
| 单元测试覆盖 | — | 130 全部通过 |

### 待办

- [ ] 子任务拆解准确率评测（76.9% → ≥85%）
- [ ] 端到端耗时基准测试（目标 ≤30s）
- [ ] DataQuery 完善度提升（60%→80%，改善结构化提取准确率）

---

## 模块三：MCP 工具集成 🚧（7/5 已完成核心开发）

> 财务公式库已在模块二的 `financial_calc.py` 中实现（19公式/7大类）。
> MCP 聚焦**外部数据源接入**，不重复造公式轮子。

### 当前状态

| 工具 | 功能 | 文件 | 状态 |
|------|------|------|:--:|
| stock_price | 股票实时行情/历史K线 | tools/stock_price.py | ✅ |
| financial_statements | 利润表/资产负债表/现金流 | tools/financial_statements.py | ✅ |
| calculate_ratio | 批量15个财务比率（复用 financial_calc） | tools/calculate_ratio.py | ✅ |
| industry_comparison | 同行业5家公司对比（白酒/新能源/互联网） | tools/industry_comparison.py | ✅ |
| market_index | 上证/沪深300/深证/创业板/行业指数 | tools/market_index.py | ✅ |
| financial_calendar | 财报日历/分红/股东大会 | tools/financial_calendar.py | ✅ |

### 已交付
- ✅ 6 个 MCP 工具全部实现（P0/P1/P2），22 测试通过
- ✅ Mock 数据覆盖茅台/比亚迪/腾讯（行情+报表+行业+指数+日历）
- ✅ Agent 集成完成（TaskType扩展 + tool_map注册 + LLM prompt + 前端）
- ✅ calculate_ratio 复用 financial_calc 的 19 个公式（零重复代码）
- ✅ ToolRegistry 增至 9 个注册工具（3原有 + 6MCP）

### 待办
- [ ] 真实 API 接入（Wind/同花顺，需 API Key）
- [ ] 前端丰富（图表展示/历史数据可视化）
- [ ] 新增 MCP 模板（市场行情分析/行业对标报告）

### 验收指标

| 指标 | 目标 | 当前 |
|------|:----:|:----:|
| MCP Tool 注册数量 | ≥6 | ✅ 6 |
| Mock 数据覆盖率 | 100% | ✅ 100% |
| Agent 透明桥接 | 零改动接入 | ✅ ToolRegistry.register() |
| 单元测试 | ≥18 | ✅ 22 |

## 技术栈

| 层级 | 选型 |
|------|------|
| 大模型 | DeepSeek v4（flash 简单 / pro 复杂） |
| Embedding | BAAI/bge-base-zh-v1.5（本地免费） |
| Reranker | BAAI/bge-reranker-v2-m3（本地免费） |
| 向量库 | ChromaDB（HNSW） |
| 分词 | jieba + 138 财务术语词典 |
| 后端 | Python 3.12 + FastAPI |
| 前端 | Streamlit |
| Agent 框架 | LangGraph StateGraph（顶层编排 + 层内 ThreadPoolExecutor 并行） |
| 业务数据库 | MySQL（V2 计划） |

---

## 关键决策记录

1. **API Key 安全**：`.env` 在 `.gitignore` 中，不会被推送
2. **模型选择**：使用 DeepSeek v4-flash / v4-pro
3. **Embedding**：本地 BGE 模型，零成本 + 数据不出本地
4. **向量库**：ChromaDB 轻量免运维，后续可迁移 Milvus
5. **分块参数**：chunk_size=800, overlap=150（实验验证最优）
6. **BM25 分词**：jieba 精确模式 + 138 财务术语词典
7. **评测体系**：50题标准集（双轨关键词+语义） + R@k/MRR/NDCG + LLM评测（Context Recall/Faithfulness）
8. **检索策略**：默认 LambdaMART 重排（+8.5pp），极短问候降级 simple，GPU加速6.7x
9. **分层架构**：rag/ + agent/ + utils/ + api/ + middleware/ + tests/，职责清晰，可独立迭代

---

## 版本路线

| 版本 | 交付 | 状态 |
|------|------|:----:|
| V1.0 | 模块一：RAG 知识库 + 评测体系 | ✅ |
| V1.5 | 前端流式 + BRD + 架构图 + PROGRESS 三模块化 + 多轮对话 + 33题测试集 | ✅ |
| V2.0 | 鉴权 + 多轮对话 + PDF表格结构化 + 测试防线 + 性能优化 | ✅ |
| V2.5 | 模块二 MVP：Agent 框架 + NL查询 + 基础报告 | ✅ 已完成 |
| V3.0 | 模块二完整：LangGraph DAG并行 + 模板库 + 追问澄清 | ✅ 阶段四完成，阶段五待启动 |
| V3.5 | 模块三：MCP Server + AKShare真实数据 | ✅ 阶段三完成 |
| V4.0 | 全平台联调 + Docker + CI/CD + 集成测试 | ✅ 阶段四完成 |
| V3.5 | 模块三：MCP Server + Wind/同花顺 + 财务公式库 | ⏳ |
| V4.0 | 全平台联调 + 端到端智能分析 + 多租户 | ⏳ |

---

## 启动方式

```bash
# 终端 1：后端
cd D:\实战项目\financial-ai-platform
python backend\main.py

# 终端 2：前端
streamlit run frontend\app.py
```

---

## 历史记录

### 2026-07-06 — 阶段五完成 + P1 清零 + rag 惰性加载 ✅

#### 5.1 agent/api.py 重构
- `agent/api.py`（新建）：公共接口集中定义，`BUILTIN_TEMPLATES` 惰性加载（CI 兼容）
- `agent/__init__.py`：42行 → 22行，`__getattr__` 仅用于 BUILTIN_TEMPLATES
- `agent/tools/__init__.py`：文档重写

#### 5.2 统一评测
- `evaluation/full_eval.py`（新建）：一键跑 RAG + Agent + MCP + 写 JSON 报告

#### 六维 Agent 审计 → 待办清单阶段六
- 对照 6 项含金量标准审计，得分 **7.5/10**
- 产出 P0-P3 改进项：上下文管理(P0)、成本追踪(P1)、人机协同(P2) 等

#### P1 修复（6 项全部清零）
| 问题 | 修复 | 文件 |
|------|------|------|
| SSE task_start 缺失 | graph.py 发出事件 | `graph.py` |
| 20 处 except:pass | → logger.warning/debug | 9 文件 |
| 流式 API 异常断连 | event_generator 加 try/except | `api/agent.py` |
| vector_store 死代码 | 删除 return 后不可达行 | `vector_store.py` |
| 评测分歧分析空壳 | per_question 存储 + 分类输出 | `quick_eval.py` |
| CI 测试覆盖不足 | 7→11 文件, 171→299 tests | `test.yml` |

#### GPU 可选化
- `hybrid_search.py`: `CrossEncoder(device="cuda")` 写死 → `torch.cuda.is_available()` 自动检测
- `rag/__init__.py`: `import sentence_transformers` → `try/except ImportError`
- `embedder.py`: 已有自动检测，注释更新
- 效果：有 GPU 加速，无 GPU 正常运行，不崩溃

#### rag/__init__.py 惰性加载
- 28 个导出：9 行 from import → `__getattr__` + 模块映射表
- `import rag` 不再触发 pymupdf/chromadb/sentence_transformers
- 370 测试全过，零功能回归

#### CI 演进
```
改前:  5 文件, 132 tests, 36% 覆盖
改后: 11 文件, 299 tests, 81% 覆盖 (+2.3x)
```
- 仍排除 4 个（运行时需要 chromadb/pymupdf/sentence_transformers）

#### Agent 20 题全量评测（2026-07-06 正式运行）

| 指标 | 当前值 | 目标 | 达标? | 变化 |
|------|:--:|:--:|:--:|:--:|
| 子任务拆解准确率 | **77.2%** | ≥85% | ❌ | +0.3pp (76.9→77.2) |
| 指标覆盖率 | **78.6%** | ≥80% | ❌ | -8.0pp (86.6→78.6) |
| 报告结构完整性 | **67.0%** | ≥80% | ❌ | 新指标 |
| 端到端平均耗时 | **54.5s** | ≤30s | ❌ | -0.4s (54.9→54.5) |

按难度：easy 82.2%/89.2%/40.4s | medium 89.5%/93.1%/60.6s | hard **39.6%/42.9%/76.7s**
按类别：杜邦 92.1% 最佳，风险扫描 65.6% 最差，盈利能力 100% 指标覆盖率

**性能瓶颈分析**（总耗时 24.6min/20题）：
1. Flash JSON 提取失败率 ~40% → 每次触发 Pro 重试 (+20-60s)
2. IndustryComparisonTool 参数缺失：Planner 拼的参数名不匹配 → 任务失败
3. Hard 题 Planner 用 Pro 模型拆解（complex 路由），单次 30-45s
4. 串行 data_query 多次 LLM 调用（检索→Flash提取→Pro兜底）→ 每题 2-4 次 LLM 往返

### 2026-07-05 — 阶段四完成：Docker + Redis + CI/CD + 集成测试 ✅

#### Docker 容器化
- `Dockerfile.backend` + `Dockerfile.frontend`：Python 3.12-slim，GPU 可选
- `docker-compose.yml`：backend + frontend + redis 三服务编排，数据卷持久化

#### Redis 集成
- `utils/redis_client.py`：Redis/内存双模式
- RateLimiter：Redis sorted set 滑动窗口 + 内存回退
- SessionStore：Redis TTL 会话 + 内存回退
- 中间件改造：auth.py 删除旧内存 RateLimiter，切换到 get_limiter()

#### CI/CD
- `.github/workflows/test.yml`：GitHub Actions 自动测试（push/PR 触发）

#### 集成测试（13 用例）
- RAG 全链路(3) + Agent 模板/报告(2) + MCP 工具注册(2)
- 依赖注入管道(1) + 工具层(2) + 健康检查(3)
- 220 测试全过

### 2026-07-05 — 阶段三完成：MCP 6工具 + AKShare 真实数据 ✅

#### MCP 模块（12 文件）
- 6 个工具：stock_price / financial_statements / calculate_ratio / industry_comparison / market_index / financial_calendar
- AKShare 数据源：新浪(行情/报表/指数) + 巨潮(分红) 真实数据，东财不可用时 Mock 兜底
- calculate_ratio 复用 financial_calc 公式库（零重复）

#### 知识库扩容
- 从 3 份 → 9 份文档（+茅台2023/比亚迪2023/五粮液/宁德时代/白酒研报）
- 4066 chunks，SEM-R@5=95.2% 纹丝不动
- 多轮对话改写 + 术语展开 bug 修复 + 引用格式 [^N] 脚注

#### GPU 全链路
- BGE Embedding CPU→GPU，单题 10s→2.6s（3.8x）
- CrossEncoder 已在 GPU，全链路 GPU 化

#### 知识库管理 + 可观测性
- corpus_manager：增量更新 + 质量检查 + 版本快照
- monitor：RequestTracker(P50/P95/P99) + 健康检查 + 告警阈值
- 前端文档管理页升级为管理面板

### 2026-07-05 — 阶段四完成：Docker + Redis + CI/CD + 集成测试 ✅

#### Docker 容器化
- `Dockerfile.backend` + `Dockerfile.frontend`：Python 3.12-slim，GPU 可选
- `docker-compose.yml`：backend + frontend + redis 三服务编排，数据卷持久化

#### Redis 集成
- `utils/redis_client.py`：Redis/内存双模式（限流器 + 会话存储）
- 中间件改造：auth.py 切换到 get_limiter()

#### CI/CD
- `.github/workflows/test.yml`：GitHub Actions 自动测试
- `requirements-ci.txt`：CI 轻量依赖（无 GPU/LLM/ChromaDB）
- agent/__init__.py + tools/__init__.py 懒加载（CI 兼容）
- Agent 评测 3 轮迭代：63.2% → 72.9% → 77.4%

#### 增量索引
- `vector_store.py`：新增 `delete_document()` 按文档名删除
- `corpus_manager.py`：incremental_rebuild() 端到端可用
- 新增文件时 2 分钟增量 vs 20 分钟全量

### 2026-07-05 — 阶段二完成：智能依赖注入 + 重试机制 + 结构化日志 ✅

#### 2.1 智能依赖注入三层回退
- **文件**：新建 `backend/agent/tools/param_injection.py`（404行）
- **Level1 精确映射**：60+对中→英财务术语映射表（营业收入→revenue 等）
- **Level2 编辑距离模糊匹配**：纯 Python Levenshtein 实现，≤2字符自动匹配，平局保守拒绝
- **Level3 LLM 批量语义匹配**：collect→batch→cache，对未匹配键名批量调用 flash 模型推断
- **命中率统计**：level1/2/3/miss 分布 + 百分比，支持 `get_stats()` 查询
- **executor.py 改造**：`_inject_dependency_data` 委托 ParamInjector.inject()，代码精简 70+ 行
- **41 个单元测试**：编辑距离/数值解析/三层匹配/注入/统计/映射表完整性

#### 2.2 错误恢复与重试机制
- **文件**：新建 `backend/utils/retry.py`（307行）
- **@retry 装饰器**：指数退避（默认3次, 1s→2s→4s），429限流自动延长等待
- **CircuitBreaker 熔断器**：CLOSED→OPEN（连续5次失败）→HALF_OPEN（冷却60s）→CLOSED
- **llm_retry**：LLM API 专用预配置，集成到 `chat()` 函数
- **DAG 失败不阻塞**：阶段一已实现（ThreadPoolExecutor + as_completed），确认生效
- **19 个单元测试**：重试成功/失败/退避时序/熔断状态机/半开探测/429限流

#### 2.3 结构化日志系统
- **文件**：新建 `backend/utils/logger.py`（226行）
- **trace_id 全链路**：contextvars 实现，format callable 实时读取，零侵入兼容所有现有 `logger.info()` 调用
- **双通道输出**：控制台(彩色) + 文件(JSON序列化, 按天轮转, 保留7天, gz压缩)
- **TraceTimer**：上下文管理器，planner/executor/reporter 三节点计时
- **RequestLogContext**：请求级日志上下文，自动生成 trace_id + 开始/结束/异常日志
- **graph.py 集成**：每个请求自动生成 trace_id + 节点计时 + DAG每层耗时
- **15 个单元测试**：trace_id/get/set/TraceTimer/RequestLogContext/setup

#### 文件变更汇总
- 新建：`param_injection.py`, `retry.py`, `logger.py`, `test_param_injection.py`, `test_retry.py`, `test_logger.py`
- 修改：`executor.py`, `model_router.py`, `graph.py`
- 阶段二 **130 测试全部通过**（41 + 19 + 15 + 40 + 15），零回归

### 2026-07-04 — 阶段一完成：6项关键Bug修复 + LangGraph架构重构 ✅

#### 架构决策
- **撤回自研方案，采用 LangGraph StateGraph**：业界标准 Agent 编排框架
  - StateGraph 做顶层编排（planner→executor→reporter）
  - ThreadPoolExecutor 做同层任务并行（DAG 拓扑排序）
  - 面试讲法："2026年主流方案是 LangGraph + 层内并行，我选择这个组合因为..."

#### 6项修复清单
| # | 修复项 | 文件 |
|:--:|------|------|
| 1.1 | 柱状图数据格式兼容（labels+values→categories+series） | chart.py |
| 1.2 | 流式执行依赖失败检查（与 sync 路径一致） | graph.py |
| 1.3 | 移除 LangGraph 死代码 → 正式接入 StateGraph | graph.py |
| 1.4 | LLM 调用路径统一（删除 get_langchain_llm，全用 chat()） | planner.py, reporter.py, data_query.py, model_router.py |
| 1.5 | DAG 拓扑排序 + 层内并行执行 | graph.py（新增 _topological_layers） |
| 1.6 | Flash JSON 提取失败→pro 重试 | data_query.py |

#### 额外优化
- 清理 `get_langchain_llm` 死代码（reporter.py, data_query.py, model_router.py）
- 修复版本号不一致（main.py 0.1.0/0.3.0 → 0.4.0）
- 图表 x 轴标签增加 rotation 避免重叠
- Planner 测试改为 mock `chat()` 适配新架构
- 55 个测试全部通过

#### 文件变更
- 重写：`graph.py`（LangGraph StateGraph + DAG并行）
- 修改：`chart.py`, `planner.py`, `reporter.py`, `data_query.py`, `model_router.py`, `config.py`, `main.py`, `executor.py`, 测试文件 × 2
- 清理：`graph.py` 删除 ~140 行死代码

### 2026-07-04 — 模块二 P0 验收补全 + Agent 核心修复 ✅

#### 新增分析模板（2 套）
- **现金流分析模板 (cash_flow)**：三大现金流查询 + FCF + 利润质量比率 + 柱状图 + 综合评估，6 个子任务
- **财务风险扫描模板 (risk_scan)**：杠杆/流动/偿债四维雷达扫描 + 风险等级预警，8 个子任务
- 前端下拉菜单同步更新（5 个模板可选）

#### 核心修复
- **依赖注入映射层**：DataQuery 中文键名（如"营业收入"）→ 公式英文参数（revenue），30+ 对映射 + 单位解析（"1709.90亿元"→1709.90）
  - 根因：LLM 提取返回中文键名+单位字符串，公式参数期望英文+纯数值，中间缺一层转换
- **LLM 速度优化**：Agent 组件（Planner/DataQuery）切换 deepseek-v4-flash，预估 Planner 从 ~44s 降至 ~3-5s
  - model_router.py 新增 TaskType 分离（SIMPLE=flash, COMPLEX=pro）
  - config.py 新增 AGENT_LLM_MODEL 配置项
- **测试运行器**：`scripts/run_tests.py` 解决 pytest CLI 模式下的 CUDA segfault（PyTorch 2.6+cu124 DLL 冲突）
  - 根因：pytest 插件先于 conftest.py 加载，sentence_transformers 的 CUDA 初始化被抢先，导致 access violation
  - 修复：在 import pytest 之前预导入 sentence_transformers

#### 测试与验证
- 55 个单元测试全部通过（公式 40 + Planner 15）
- 新增 2 个模板测试（现金流模板结构 + 风险扫描模板结构）
- LLM 提示词补全全部 19 个公式（之前只列了 10 个）

#### 文件变更
- 修改：`planner.py`, `executor.py`, `model_router.py`, `config.py`, `data_query.py`, `test_agent_planner.py`, `test_agent_financial_calc.py`, `conftest.py`, `frontend/app.py`, `PROGRESS.md`
- 新增：`scripts/run_tests.py`

### 2026-07-02 — 模块二 V2.5 MVP 完成 ✅

#### 核心交付
- **Agent 框架**：自研轻量编排（Planner→Executor→Reporter），不依赖 LangGraph 完整框架
- **财务公式库**：19 个内置公式（盈利能力 5/偿债能力 4/营运 3/成长 3/估值 2/现金流 2/杜邦 1），纯 Python 零外部依赖
- **图表工具**：5 种图表（折线/柱状/饼图/雷达/双轴），matplotlib Agg 后端 + 中文字体自动适配
- **分析模板**：3 个预设模板（盈利能力评估/杜邦分析/成长性分析）
- **SSE 流式分析**：7 种事件类型
- **前端 UI**：替换占位页面，SSE 流式进度 + Markdown 报告渲染 + 图表展示

#### 测试与验证
- 53 个单元测试全部通过（财务公式 40 + Planner 13）
- API 4 端点验证通过，模块一 RAG 功能不受影响
- 50 题评测脚本已就绪（scripts/quick_eval_50.py），评测进行中（每条约 10s+）

#### 待办清单调整
- ❌ Entity Routing 全链路开发 — 已删除（实验验证负收益 -2.7pp）
- ↓ Docker 容器化 — 降级至 P1
- ✅ 采纳建议的 P0 精简方案（4 项 → 本周可完成）

#### 文件统计
- 新建 15 个文件，修改 7 个文件，+2929 行代码
- 21 files changed in commit 089de3c

### 2026-07-01 — 模块一完整功能验证 + 性能优化 ✅

#### 端到端功能验证
- 后端 7 端点全部正常（health/docs/upload/chat/chat-stream/documents/evaluate）
- 实际问答测试通过："茅台营收多少" → 1,741.44 亿元 + 5 个来源溯源
- 检索评测：10 题抽样 R@5=81.0%，MRR=80.3%
- 鉴权：X-API-Key 校验正常（无 Key→401，正确 Key→200）
- 限流：超限返回 429 + Retry-After
- 前端 `localhost:8501` 已启动

#### 速度优化（30s → 10-13s，-60%）
| 优化 | 效果 | 准确率影响 |
|------|:--:|:--:|
| BM25 索引缓存 | 每次省 7s | 无影响 |
| LambdaMART 候选裁剪 | 尝试省 10s，R@5 跌 9.3pp | **已回滚** |

#### 切片阈值优化（mean-0.5std → mean-1std）
- 根因诊断：52% chunk < 300 字，页眉/目录等垃圾前缀污染财务数据
- Q02 "归母净利润" 正确答案排在 RRF 第 13 位（被垃圾前缀拖低语义分数）
- 优化：总 chunks 2882→1964（-32%），平均长度 403→510 字（+26%）
- 需重建索引后重跑评测验证新基线

#### 今日全量
- 新增测试：鉴权 17 题 + 表格 20 题 + 数据集验证 17 题 = 54 题
- 全量测试：196 用例通过
- Git 提交：9 次

### 2026-07-01 — 测试集扩充 33→50 题 ✅

**新增 17 题（Q34-Q50）**：

| 维度 | 33题→50题变化 |
|------|------|
| 比亚迪专项 | 1→6题 (+5) |
| 腾讯专项 | 1→5题 (+4) |
| 跨文档检索 | 1→4题 (+3) |
| 综合分析/推理 | 2→5题 (+3) |
| 风险分析 | 2→4题 (+2) |

**50题分布**：数值查询11+趋势分析7+对比分析5+跨文档4+综合分析3+综合推理2+风险分析4+定义解释4+边界异常5+脏数据5

**新增测试**：`test_dataset.py` 17 用例（结构校验4+内容校验5+覆盖度6+跨文档2）

### 2026-07-01 — PDF 表格结构化提取验收 ✅

**验收数据（3份年报）**：
| 年报 | 页数 | 表格总数 | 大表(≥4×3) | 最大表 | Col1率 |
|------|:--:|:--:|:--:|------|:--:|
| 比亚迪 | 290 | 250 | 145 | 42行×29列 | 68% |
| 茅台 | 143 | 275 | 180 | 50行×16列 | 19% |
| 腾讯 | 272 | 22 | 17 | 30行×9列 | 35% |

**结论**：PyMuPDF find_tables() → Markdown 方案通过验收。
- 表格检测覆盖率优秀，核心财务数据正确提取
- Markdown 格式标准（pipe + 分隔行），LLM 可直接理解
- 大表格（≥4行×3列）正确注入语义分块
- 已知局限：复杂合并单元格表头有 Col1 占位符（比亚迪68%，茅台仅19%），
  不影响检索和问答（数据单元格正确提取），后续可用 pymupdf_layout 改进

**新增测试**：`test_table_extraction.py` 20 用例（检测/格式/注入/切分兼容/降级容错）

### 2026-07-01 — API 鉴权 + 限流 ✅

- 新增 `backend/middleware/auth.py`：SecurityMiddleware（鉴权+限流一体）
- X-API-Key Header 鉴权，API_KEY 为空=开发模式
- 内存滑动窗口限流器：按 IP+接口类型计数（通用 30/min，Chat 10/min）
- 支持 X-Forwarded-For 获取真实 IP
- `/health` `/docs` 公开路径跳过拦截
- 所有参数通过 `.env` + `config.py` 管理
- 测试：`test_auth.py` 17 用例（鉴权 8 + 限流 4 + 边界 2 + 配置 3）
- 全量测试：159 用例全部通过

### 2026-07-01 — 单元测试防线搭建 ✅

#### 测试框架
- 安装 pytest + pytest-cov，加入 `requirements.txt`
- 新建 `backend/tests/` 目录，含 `conftest.py`（自动处理 Python path）

#### 四个核心组件测试（142 用例全部通过）

| 组件 | 用例数 | 覆盖要点 |
|------|:--:|------|
| `entity_router.py` | 29 | 实体识别、跨文档判断、文档过滤、文件名反向匹配、BM25 加权源、注册表一致性 |
| `evaluator.py` | 49 | 文本归一化(9)、R@k(7)、Precision(4)、MRR(4)、NDCG@k(4)、LLM 评测 mock(6)、批量评测(3) |
| `query_processor.py` | 29 | 术语展开(12)、余弦相似度(4)、LLM 扩写 mock(3)、校验 mock(2)、集成流程(5) |
| `hybrid_search.py` | 35 | 策略路由(12)、RRF 融合(7)、LambdaMART 重排 mock(4)、BM25/semantic mock(6)、集成流程(6) |

- 运行方式：`pytest backend/tests/ -v`（全量 ~10s）
- 所有外部依赖（LLM/Embedding/ChromaDB/CrossEncoder）均通过 `unittest.mock` 隔离

---

### 2026-07-01 — 前端重构 + PROGRESS 三模块化

#### 前端流式输出 ✅
- 后端新增 `POST /api/v1/rag/chat/stream` SSE 端点
- `model_router.py` 新增 `chat_stream()` 流式调用
- 前端重写：逐字流式显示、对话历史保留、三模块导航
- Agent 和 MCP 页面设占位预览（展示完整产品愿景）
- **缓存优化**：`session_state` 缓存后端状态 + 文档列表（30s TTL），页面切换不再卡顿

#### 业务数据库（SQLite）✅
- 新建 `backend/db/` 模块（SQLAlchemy ORM）
- `documents` 表：文档元数据（文件名/大小/页数/块数/上传时间）
- `chat_history` 表：对话记录持久化
- `query_log` 表：查询日志（审计 + 统计分析）
- 上传时自动写入 documents 表；每次查询记录到 query_log
- 文档列表优先从数据库读取，数据库不可用时回退 ChromaDB
- 架构预留 MySQL 切换（改一行连接串即可）

#### PROGRESS.md 重构 ✅
- 按三模块拆分：模块一(RAG) / 模块二(Agent) / 模块三(MCP)
- 每模块独立状态表 + 验收指标 + 待办
- 模块一 RAG 细节从 18 行精简为 12 行
- 模块二/三预留完整跟踪结构

#### 项目文档 ✅
- `docs/BRD-业务需求说明书.md`：10章完整业务需求
- `docs/架构图.md`：7张 Mermaid 架构图

---

### 2026-06-30 — RAG 多文档检索优化（4轮迭代达到 87.3%）

| 轮次 | 改动 | R@5 | MRR | 结论 |
|:----:|------|-----|-----|------|
| 0 | 多文档基线（3份年报，1443 chunks）| 77.1% | 82.9% | 检索空间膨胀 |
| 1 | P0 数字归一化 | 78.8% | 82.9% | +1.7pp |
| 2 | P1 术语展开 | 78.8% | 82.9% | 无增益 |
| 3 | Entity Routing + 强制重排 | 74.4% | 80.8% | -2.7pp |
| **4** | **默认LambdaMART重排 + 关键词补全** | **87.3%** | **90.8%** | **+10.2pp** |

详细记录见 git log 2026-06-30 的提交。

---

### 2026-06-30 — RAG 基础能力完善

- BM25 jieba 分词 + 138 财务术语词典
- 20 题标准测试集（6类 × 3难度）
- 评测体系升级（R@k/MRR/NDCG + 按难度/类别统计）
- 4 组参数对比实验脚本
- 参数可配置化（.env → config.py）
- API 评测接口

---

### 2026-06-29 — RAG Pipeline 核心实现

- 多格式文档加载（PDF/Word/MD/TXT）
- 语义动态切分
- BGE Embedding + ChromaDB
- 混合检索（语义 + BM25 + RRF + Reranker）
- Query 处理（扩写 + 余弦校验）
- 模型路由
- 基础前端
