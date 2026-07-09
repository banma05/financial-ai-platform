# 📊 智能财务分析平台

> **SQL 优先，RAG 辅助，Agent 驱动 — 自然语言驱动的财务数据分析助手**

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139-green)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-purple)](https://langchain-ai.github.io/langgraph/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek_v4-purple)](https://www.deepseek.com/)
[![Tests](https://img.shields.io/badge/Tests-162%2F162-green)]()

---

## 🎯 一句话

输入 **"分析茅台 2024 年盈利能力"** → 秒级返回 **数字 + 图表 + 原文引用的专业分析报告**。

---

## 🏗️ 架构 (V8.0)

```
用户上传文档(年报/研报/尽调)
  → loader 解析表格+正文
  → 表格 → 规则提取 → SQL (100%准确)
  → 正文 → RAG 索引 (可溯源引用)
  → Agent: Planner → Executor(SQL+RAG+Calc+Chart) → Reporter
  → 数字 + 解读 + 图表 + 原文引用 = 完整报告
```

### 核心设计决策

| 决策 | 理由 |
|------|------|
| **数字不走 LLM** | 表格→规则提取→SQL，100% 准确，<2ms |
| **RAG 做溯源，不做提取** | 引用原文页码，不猜数字 |
| **三个任务类型互补** | data_query(数字) + rag_context(解读) + calculate(公式) |
| **诚实评测** | 区分能力内/外，不过拟合 |

---

## 📊 评测基线 (V8.0)

| 指标 | 值 | 说明 |
|------|:--:|------|
| SQL 覆盖率 | **100%** | 单/多公司+多年份，24/24 |
| 平均延迟 | **1.4ms** | 零 LLM |
| 规则提取准确率 | **100%** | 茅台56指标全匹配年报 |
| 多公司查询 | ✅ | 茅台 vs 五粮液等 |
| Agent 任务类型 | **4种** | +rag_context(原文解读) |
| 测试 | **162/162** | CI 通过 |

---

## 🚀 快速启动

```bash
cd D:\实战项目\financial-ai-platform
source ../.venv/Scripts/activate   # 激活虚拟环境
pip install -r requirements.txt    # 首次安装依赖
python backend/main.py             # 后端 :8001
streamlit run frontend/app.py      # 前端 :8501 (即将替换为 React)
```

## 📁 项目结构

```
financial-ai-platform/
├── backend/
│   ├── agent/         # Agent 引擎 (Planner/Executor/Reporter + 4工具)
│   ├── rag/           # RAG 引擎 (loader/splitter/embedder/retriever/table_extractor)
│   ├── db/            # SQLite + 财务数据模型 + 查询引擎
│   ├── mcp/           # MCP 6工具 (AKShare)
│   ├── api/           # FastAPI 路由 (上传/分析/问答)
│   ├── utils/         # 重试/日志/监控
│   └── tests/         # 162 单元测试
├── frontend/          # Streamlit (→ 即将替换为 React)
├── evaluation/        # 50题三层评测 + 运行器
├── docs/              # BRD/架构图/V8实施计划
└── data/              # 文档/ChromaDB/模型
```

## 📝 文档

- [V8.0 实施计划](docs/V8-实施计划.md)
- [BRD 业务需求说明书](docs/BRD-业务需求说明书.md)
- [系统架构图](docs/架构图.md)
- [项目进度](PROGRESS.md)
