# 📊 智能财务分析平台

> **数据准确可溯源，分析有据可审查 — 真正会做基本面分析的 AI**

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139-green)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React_19-blue)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-purple)](https://langchain-ai.github.io/langgraph/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek_v4-purple)](https://www.deepseek.com/)
[![Version](https://img.shields.io/badge/Version-V9.2-blue)]()
[![Tests](https://img.shields.io/badge/Tests-461_backend-green)]()

---

## 🎯 一句话

输入 **"分析茅台2024年盈利能力"** → 秒级返回 **数字可溯源 + 图表可交互 + 年报原文引用** 的专业分析报告。

---

## 🏗️ 架构 (V9.2)

```
用户自然语言输入
  → Planner: 模板匹配(<0.1s) 或 LLM 自由拆解
  → Executor: SQL查数字(毫秒级) + RAG查解读(原文引用) + 公式计算(Python零LLM) + 图表生成(ECharts)
  → Reporter: 6章研报 + 数据溯源 + 置信度标注 + 幻觉检测
  → 输出: 数字准确可溯源 + 图表可交互 + 年报原文引用 + 行业基准对比
```

### 核心设计决策

| 决策 | 理由 |
|------|------|
| **数字不走 LLM** | 表格→规则提取→SQL，100% 准确，<2ms |
| **RAG 做溯源，不做提取** | 引用原文页码，不猜数字 |
| **三层数据质量** | SQL直查(高置信度) → fallback回退(中) → computed推算(低) |
| **每数字可溯源** | 来源标注(sql/fallback/computed) + 动态置信度 |
| **模板优先** | 高频场景0.1s命中，质量100%可控 |
| **图表智能降级** | ≤1数据点自动跳过+说明，零空白 |
| **报告可审查** | 数据可靠度章节 + 数值校验 + 幻觉检测 |
| **诚实透明** | 已知限制公开，RAG覆盖不足主动标注 |

---

## 📊 评测基线 (V9.2 · 2026-08-28 实测)

### Agent 端到端（50 题全量 · 7 维评分）

| 指标 | 值 | 目标 | 状态 |
|------|:--:|:--:|:--:|
| 锚点准确率（独立验证） | **96.0%** | ≥95% | ✅ 首次达标 |
| 数值准确率 | **95.0%** | ≥85% | ✅ |
| 幻觉检测 | **96.5%** | ≥90% | ✅ |
| 溯源率 | **91.1%** | ≥80% | ✅ |
| 图表渲染率 | **96.0%** | ≥90% | ✅ |
| 结构覆盖 | 79.2% | ≥80% | ⚠️ 差 0.8pp |
| 综合评分 | 79.7% | ≥85% | ⚠️ 差 5.3pp |

> 50/50 完成、0 崩溃；单题成本 ≈ ¥0.06（DeepSeek 官方价格记账）。锚点验证以 15 个独立核实的数字为"地面真相"，打破循环论证。

### RAG 评测（RAGAS 三指标）

| 指标 | 值 | 目标 | 状态 |
|------|:--:|:--:|:--:|
| SEM-R@5（检索） | **96.0%** | ≥90% | ✅ |
| Faithfulness | **94.1%** | ≥90% | ✅ |
| Answer Relevancy | 47.3% | ≥85% | ⚠️ |
| Context Recall | 50.0% | ≥85% | ⚠️ |

### 关键验证

| 维度 | 指标 |
|------|------|
| 贵州茅台 profitability | 毛利率 91.18% 净利率 48.76% ROE 33.65% ✅ |
| Chart 零空白 | 3 数据点柱状图, skip=None ✅ |
| 报告可审查 | 数据可靠度章节 + 溯源信息 + 置信度 ✅ |
| 后端单元测试 | **461/461** ✅ |
| 前端单元测试 | **20/20** ✅ + TypeScript 0 错误 |

### 已知限制（诚实透明）

| # | 限制 | 影响 |
|:--:|------|------|
| 1 | 综合评分 79.7% 未达 85% | 自由拆解 20 题中 9 题 LLM 拆解空响应回退，综合 30-50% 拉低平均 |
| 2 | RAG Answer Relevancy / Context Recall 偏低 | 数值类问题的评测集与抽取逻辑待优化 |
| 3 | Agent 高并发下接近串行 | LLM API 外部瓶颈 + 模型资源锁 |
| 4 | 仅覆盖 20 家 A 股公司 + 14 份年报 | 扩展至 5000 家需迁移 PostgreSQL |
| 5 | 跨公司对比仅取第一家公司 | "对比茅台和五粮液"只返回茅台数据 |

---

## 🚀 快速启动

```bash
# 环境准备：复制 .env.example 为 .env 并填入 DeepSeek API Key
cp .env.example .env

# 后端 :8001（Python 3.12 虚拟环境）
pip install -r requirements.txt
python -m backend.main

# 前端 :5173（开发模式，自动代理 /api → :8001）
cd web && npm install && npm run dev
```

## 🧪 测试

```bash
# 后端 461 单元测试
python scripts/run_tests.py

# Agent 评测（V9 50题 或 V8 15题）
python evaluation/agent/bench_agent_v9.py           # V9 全量
python evaluation/agent/bench_agent_v9.py --quick   # 快速抽检5题
python evaluation/agent/bench_agent_v9.py --dataset v8  # 旧版兼容

# RAG 评测
python evaluation/rag/quick_eval.py
```

## 📁 项目结构

```
financial-ai-platform/
├── backend/                # FastAPI 后端 (:8001)
│   ├── agent/              # LangGraph Agent (Planner→Executor→Reporter)
│   │   ├── planner.py      # 模板加载 + LLM 自由拆解
│   │   ├── executor.py     # 依赖注入分两路(图表直注+公式ParamInjector)
│   │   ├── reporter.py     # 6章研报 + 数据可靠度 + 幻觉检测
│   │   └── tools/          # data_query / financial_calc / chart / param_injection / rag_context
│   ├── rag/                # RAG 引擎 (BM25+语义+ChromaDB+重排序+模型路由)
│   ├── db/                 # SQLite + 财务数据模型 + 金融查询引擎
│   ├── mcp/                # MCP 6工具 (AKShare数据源)
│   ├── api/                # FastAPI 路由 (agent + rag)
│   ├── models/             # Pydantic 数据模型
│   ├── di/                 # 应用级 DI 容器 (Container + Repository)
│   ├── security/           # InputSanitizer 输入清洗
│   ├── middleware/         # 鉴权 + 限流
│   ├── utils/              # 重试/日志/监控/Redis
│   └── tests/              # 461 单元测试
├── web/                    # React 前端 (Vite + TypeScript + Zustand + ECharts)
│   ├── src/pages/          # 预设分析/文档上传/报告展示
│   ├── src/components/     # ChartRenderer (骨架屏+错误UI+ResizeObserver)
│   └── src/stores/         # Zustand 状态管理
├── evaluation/             # 评测体系 (50题7维评分 + RAGAS)
│   ├── agent/              # bench_agent_v9.py + bench_agent.py
│   ├── data/               # agent_questions_v9.json (50题)
│   └── rag/                # RAG 评测
├── data/                   # 文档/ChromaDB/模型缓存 (gitignore)
├── scripts/                # 运维脚本 (backfill/rebuild/import)
├── CHANGELOG.md            # 版本演进记录
└── ARCHITECTURE.md         # 架构文档
```

## 📝 文档

- [架构文档](ARCHITECTURE.md) — 整体架构 + 核心设计决策
- [版本演进](CHANGELOG.md) — 各版本核心成果与评测数据

## 🔑 技术栈速查

| 层 | 技术 | 说明 |
|------|------|------|
| LLM | DeepSeek v4-flash + v4-pro | flash(简单任务) / pro(复杂推理) |
| Embedding | BAAI/bge-base-zh-v1.5 | 768维，本地运行 |
| Reranker | BAAI/bge-reranker-v2-m3 | 本地CrossEncoder |
| 向量库 | ChromaDB + HNSW | 5097 chunks |
| 数据库 | SQLite (EAV模式) | 20家公司，2021-2026年 |
| 后端 | FastAPI + LangGraph | Python 3.12 |
| 前端 | React 19 + Vite + TypeScript | Zustand + ECharts + Tailwind |
| 数据源 | AKShare | A股财务数据 |
