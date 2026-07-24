# 📊 智能财务分析平台

> **数据准确可溯源，分析有据可审查 — 真正会做基本面分析的 AI**

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139-green)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React_19-blue)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-purple)](https://langchain-ai.github.io/langgraph/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek_v4-purple)](https://www.deepseek.com/)
[![Version](https://img.shields.io/badge/Version-V9.0--beta-orange)]()
[![Tests](https://img.shields.io/badge/Tests-96_backend-green)]()

---

## 🎯 一句话

输入 **"分析茅台2024年盈利能力"** → 秒级返回 **数字可溯源 + 图表可交互 + 年报原文引用** 的专业分析报告。

---

## 🏗️ 架构 (V9.0-beta)

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

## 📊 评测基线 (V9.0-beta)

### Agent 端到端

| 指标 | 值 | 目标 | 说明 |
|------|:--:|:--:|------|
| 综合评分 (V9 50题) | ⏳ 待跑 | ≥85% | 7维加权评分 |
| 锚点准确率 (独立验证) | ⏳ | ≥95% | 打破循环论证的核心指标 |
| 数据溯源率 (SQL直查) | — | ≥80% | 每个数字可追溯到来源 |
| 图表渲染率 | — | ≥90% | 期望图表中实际生成比例 |
| 幻觉检测 | — | ≥90% | 方向性断言与数据吻合度 |

### 基础验证

| 维度 | 指标 |
|------|------|
| 贵州茅台 profitability | 毛利率91.18% 净利率48.76% ROE33.65% ✅ |
| Chart 零空白 | 3数据点柱状图, skip=None ✅ |
| 报告可审查 | 数据可靠度章节 + 溯源信息 + 置信度 ✅ |
| planner 测试 | 15/15 ✅ |
| param_injection 测试 | 41/41 ✅ |
| financial_calc 测试 | 40/40 ✅ |

### 已知限制（诚实透明）

| # | 限制 | 影响范围 | 计划 |
|:--:|------|:--:|------|
| 1 | RAG知识库仅覆盖4/20家公司 | 非茅台/比亚迪/宁德/五粮液的分析缺年报原文解读 | P3-11: 优先补金融+大市值 |
| 2 | 跨公司对比仅取第一家公司 | "对比茅台和五粮液"只返回茅台数据 | P1-5: parse_query多公司 |
| 3 | 仅支持A股(20家公司) | 不含港股/美股 | P3-10: PostgreSQL→5000家 |
| 4 | 金融企业指标覆盖不全 | 银行/保险的部分特殊指标可能缺失 | P0-1已修复核心数据 |
| 5 | 响应时间31-67s | LLM调用是主要瓶颈 | P2-7: 模板场景<5s |

---

## 🚀 快速启动

```bash
cd D:\实战项目\financial-ai-platform

# 后端 :8001
source ../.venv/Scripts/activate
python -m backend.main

# 前端 :5173（开发模式，自动代理 /api → :8001）
cd web && npx vite
```

## 🧪 测试

```bash
# 后端 96 单元测试
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
├── backend/
│   ├── agent/              # LangGraph Agent (Planner→Executor→Reporter + 4工具)
│   │   ├── planner.py      # 模板加载 + LLM 自由拆解
│   │   ├── executor.py     # 依赖注入分两路(图表直注+公式ParamInjector)
│   │   ├── reporter.py     # 6章研报 + 数据可靠度 + 幻觉检测
│   │   └── tools/          # data_query / financial_calc / chart / param_injection
│   ├── rag/                # RAG引擎 (BM25+语义+ChromaDB+重排序)
│   ├── db/                 # SQLite + 财务数据模型 + 金融查询引擎(_KEY_FALLBACK)
│   ├── mcp/                # MCP 6工具 (AKShare数据源)
│   ├── api/                # FastAPI 路由 (agent + rag)
│   ├── models/             # Pydantic 数据模型
│   ├── utils/              # 重试/日志/监控/Redis
│   └── tests/              # 96 单元测试 (planner + param_injection + financial_calc)
├── web/                    # React 前端 (Vite + TypeScript + Zustand + ECharts)
│   ├── src/pages/          # 预设分析/文档上传/报告展示
│   ├── src/components/     # ChartRenderer (骨架屏+错误UI+ResizeObserver)
│   └── src/stores/         # Zustand 状态管理
├── evaluation/             # 评测体系 (V9: 50题7维评分)
│   ├── agent/              # bench_agent_v9.py + bench_agent.py
│   ├── data/               # agent_questions_v9.json (50题) + V8 (15题)
│   ├── rag/                # RAG 评测
│   └── reports/            # 评测报告 + 趋势追踪
├── data/                   # 文档/ChromaDB/模型缓存
├── docs/                   # 设计文档 (V9.0产品重构计划/BRD/架构图)
├── scripts/                # 运维脚本 (backfill/rebuild/import)
└── PROGRESS.md             # 详细进度记录
```

## 📝 文档

- [V9.0 产品重构计划](docs/V9.0-产品重构计划.md) — 13项任务 / 4级优先级
- [V8.0 实施计划](docs/V8-实施计划.md)
- [BRD 业务需求说明书](docs/BRD-业务需求说明书.md)
- [系统架构图](docs/架构图.md)
- [项目进度详情](PROGRESS.md)

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
