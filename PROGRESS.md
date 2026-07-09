# 智能财务分析平台 — 项目进度

> 📅 最后更新：2026-07-09 深夜
> 🎯 当前版本：**V8.0** — SQL优先 + RAG辅助 + 规则提取 + 诚实评测
> 🏗️ 状态：阶段A完成 ✅ → 阶段B待启动 (React前端)

---

## V8.0 评测基线 (2026-07-09, 诚实不粉饰)

| 维度 | V7.0 | V8.0 | 备注 |
|------|:--:|:--:|------|
| SQL 覆盖率 (能力内) | — | **100%** (24/24) | 单/多公司+多年份 |
| SQL 准确率 (能力内) | ~60% | **83.3%** (20/24) | 残差来自AKShare精度 |
| SQL 平均延迟 | 20-80s | **1.4ms** | 零LLM |
| 多公司查询 | ❌ | ✅ | 茅台vs五粮液等 |
| 规则提取 | ❌ (LLM) | **56指标,100%准确** | 零LLM,表格→SQL |
| Agent 任务类型 | 3种 | **4种** | +rag_context(原文解读) |
| 代码量 | 16,041 | 13,521 | -2,520行 |
| CI 测试 | 10失败 | ✅ 通过 | 162/162 |
| PDF loader | 74%断行率 | ✅ 7/7 | dict+坐标过滤 |
| 线程安全 | ❌ 4竞态 | ✅ DCL锁 |

## 阶段A 新增交付 (2026-07-09 深夜)

| 组件 | 文件 | 功能 |
|------|------|------|
| 规则提取引擎 | `rag/table_extractor.py` | 表格→行标签匹配→SQL, 零LLM |
| RAG上下文工具 | `agent/tools/rag_context.py` | 检索原文→LLM提炼→报告引用 |
| 上传集成 | `api/rag.py` | 上传自动触发规则提取 |

### 已知限制 (诚实)

- 口语化表达未支持 ("赚了多少钱")
- 年份默认去年 (可能不是最新年报)
- 预置公司需手动下载年报PDF

---

## 产品架构 (V8.0)

```
用户上传文档(年报/研报/尽调)
  → loader 解析表格+正文
  → 表格 → 规则提取 → SQL (100%准确)
  → 正文 → RAG 索引 (可溯源引用)
  → Agent: Planner → Executor(SQL+RAG+Calc+Chart) → Reporter
  → 数字 + 解读 + 图表 + 原文引用 = 完整报告
```

### 三阶段实施

| 阶段 | 内容 | 状态 |
|------|------|:--:|
| **A** 引擎补完 | 规则提取 + RAG任务 + 上传闭环 | ✅ |
| **B** 体验优化 | React前端 + 预设标签 + 报告展示 | ⏳ |
| **C** 质量防线 | Agent/RAG评测 + 回归验证 | ⏳ |

详细计划: `docs/V8-实施计划.md`

---

## V8.0 评测基线 (2026-07-09, 诚实不粉饰)

| 维度 | V7.0 | V8.0 | 备注 |
|------|:--:|:--:|------|
| SQL 覆盖率 (能力内) | — | **100%** (24/24) | 单/多公司+多年份 |
| SQL 准确率 (能力内) | ~60% | **83.3%** (20/24) | 剩余偏差来自AKShare精度 |
| SQL 平均延迟 | 20-80s | **1.4ms** | 零LLM |
| 多公司查询 | ❌ | ✅ | 茅台vs五粮液等|
| 代码量 | 16,041 | 13,521 | -2,520行 |
| CI 测试 | 10失败 | ✅ 通过 | test_dataset适配V8.0 |
| PDF loader | 74%断行率 | ✅ 7/7 | dict+坐标过滤 |
| 线程安全 | ❌ 4竞态 | ✅ DCL锁 |

### 已知限制 (诚实)

- 口语化表达未支持 ("赚了多少钱")
- 年份默认去年 (可能不是最新年报)
- 三家跨公司键名匹配残差
- RAG/Agent评测待跑

---

## V8.0 架构决策（2026-07-09）

### 核心理念：SQL 优先，RAG 辅助，零冗余

```
用户输入 → Planner(LLM) → Executor → Reporter(LLM) → 报告+图表
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          SQL查询        财务公式计算      可视化图表
        (毫秒级,100%准)  (Python,零LLM)  (matplotlib)
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                    RAG（辅助解读,非查数字）
```

### 三个关键决策

1. **砍掉 data_layer**（~1000行）：用 LLM 从 PDF 提取财务数字这条路不可靠。改为 AKShare API 预置 + PDF 表格规则提取。

2. **砍掉 verifier + comparator + memory**（~250行）：功能太弱，不生产价值。

3. **executor 回归线性执行**：ThreadPoolExecutor + 懒加载单例 = 竞态 + GPU OOM。不值得为 1-2 个任务并行引入线程复杂度。

---

## 项目结构（V8.0 精简后）

```
financial-ai-platform/
├── backend/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 全局配置
│   ├── agent/                   # Agent 引擎（三节点直通）
│   │   ├── graph.py             # LangGraph 编排
│   │   ├── planner.py           # 任务拆解 + 模板库
│   │   ├── executor.py          # 线性执行 + 依赖注入
│   │   ├── reporter.py          # 报告生成
│   │   ├── schemas.py           # 数据模型
│   │   └── tools/
│   │       ├── data_query.py    # SQL优先 + RAG兜底
│   │       ├── financial_calc.py # 19财务公式
│   │       ├── chart.py         # 5种图表
│   │       └── param_injection.py # 三层依赖注入
│   ├── rag/                     # RAG 引擎（辅助解读）
│   │   ├── loader.py            # 文档加载（四格式）
│   │   ├── semantic_splitter.py # 语义动态切分
│   │   ├── embedder.py          # BGE 向量化
│   │   ├── vector_store.py      # ChromaDB
│   │   ├── hybrid_search.py     # BM25+语义+RRF+LambdaMART
│   │   ├── query_processor.py   # Query 理解
│   │   ├── entity_router.py     # 实体识别+文档路由
│   │   ├── jieba_tokenizer.py   # 中文分词+138财务词典
│   │   ├── evaluator.py         # 评测体系
│   │   ├── model_router.py      # LLM 统一调用
│   │   ├── retriever.py         # RAG 问答入口
│   │   ├── keywords.py          # 财务关键词库
│   │   └── corpus_manager.py    # 知识库管理
│   ├── mcp/                     # MCP 6工具
│   │   ├── mock_data.py         # Mock 数据源
│   │   └── tools/               # 股票/财报/比率/行业/指数/日历
│   ├── db/                      # 业务数据库（SQLite）
│   ├── api/                     # FastAPI 路由
│   ├── models/                  # Pydantic 模型
│   ├── middleware/              # 鉴权+限流
│   ├── utils/                   # 重试+日志+监控+Redis
│   └── tests/                   # 单元测试
├── frontend/app.py              # Streamlit 前端
├── evaluation/                  # 评测脚本+数据集+报告
├── scripts/                     # 运维脚本
├── data/
│   ├── documents/               # 原始文档
│   ├── chroma_db/               # 向量持久化
│   └── models/                  # 本地模型
├── docs/                        # 文档
├── requirements.txt
└── .env
```

---

## 已删除模块（V8.0 清理）

| 删除的文件 | 行数 | 原因 |
|-----------|:--:|------|
| `rag/experiments.py` | 685 | 参数实验脚本，非生产代码 |
| `rag/quick_tune.py` | 326 | 与 experiments 功能重叠 |
| `rag/splitter.py` | 66 | 被 semantic_splitter 替代 |
| `agent/verifier.py` | 81 | 纯规则检查，无实际价值 |
| `agent/comparator.py` | 101 | 无 LLM 的数据提取，功能弱 |
| `agent/memory.py` | 71 | 薄包装，暂不启用 |
| `utils/topological.py` | 57 | 配合 executor 线性化删除 |
| `data_layer/` | ~1000 | 用 LLM 提取数字不可靠，重建 |
| **合计** | **~2,520** | |

---

## 历史关键基线（V7.0 之前，仅供参考）

### RAG 评测（模块一）

| 场景 | KW-R@5 | SEM-R@5 | MRR |
|------|:------:|:-------:|:---:|
| 多文档（3年报, mean-1std）| 70.4% | 95.2% | 89.5% |

> ⚠️ 注意：SEM-R@5=95.2% 是"检索到正确 chunk"的准确率，**不是答案正确率**。chunk 内容有乱码导致数字不准，这是 V8.0 要解决的核心问题。

### Agent 评测（模块二）

| 指标 | V7.0 | 目标 |
|------|:--:|:--:|
| 子任务拆解准确率 | 77.2% | ≥85% |
| 端到端平均耗时 | 54.5s | ≤10s |

---

## 启动方式

```bash
cd D:\实战项目\financial-ai-platform

# 虚拟环境
source ../.venv/Scripts/activate

# 后端
python backend/main.py

# 前端
streamlit run frontend/app.py
```

## 测试

```bash
python scripts/run_tests.py
```

---

## Git 规范

- Commit message 用中文描述改动
- 每完成功能点 commit + push
- `.env` 和 `面试准备-项目深挖点.md` 不提交
