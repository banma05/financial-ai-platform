# 📊 智能财务分析平台

> **SQL 优先，RAG 辅助，Agent 驱动 — 自然语言驱动的财务数据分析助手**

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139-green)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-purple)](https://langchain-ai.github.io/langgraph/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek_v4-purple)](https://www.deepseek.com/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-brightgreen)](https://www.trychroma.com/)
[![AKShare](https://img.shields.io/badge/Data-AKShare-red)](https://akshare.akfamily.xyz/)

---

## 🎯 一句话说清楚

输入 **"分析茅台 2024 年盈利能力"** → 秒级返回 **带图表的专业分析报告**，数字 100% 准确。

---

## 🏗️ 架构（V8.0）

```
用户输入 → Planner(LLM) → Executor → Reporter(LLM) → 报告+图表
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          SQL查数字       RAG解读文字      公式计算+图表
         (毫秒,100%准)   (BM25+语义+LLM)   (Python,零LLM)
```

### 核心设计决策

| 决策 | 理由 |
|------|------|
| **SQL 优先，不是 RAG** | 财务数字须 100% 准，LLM 做不到 |
| **RAG 做文字解读，不做数字提取** | 找原因/趋势，RAG 擅长且安全 |
| **Agent 三节点直通** | 砍掉 verifier/comparator 等中间节点 |
| **线性执行，不做层内并行** | 避免 GPU 双重加载和竞态 |

---

## 🚀 快速启动

```bash
cd D:\实战项目\financial-ai-platform

# 激活虚拟环境
source ../.venv/Scripts/activate

# 安装依赖（首次）
pip install -r requirements.txt

# 启动后端 :8001
python backend/main.py

# 启动前端 :8501
streamlit run frontend/app.py
```

---

## 📊 评测基线

| 指标 | 目标 | 说明 |
|------|:----:|------|
| 数字查询准确率 | ≥99% | SQL 直接返回 |
| 端到端耗时 | ≤10s | 提问→报告 |
| 子任务拆解准确率 | ≥85% | Planner 输出质量 |
| 测试覆盖 | ≥85% | CI 自动运行 |

---

## 📁 项目结构

```
financial-ai-platform/
├── backend/
│   ├── agent/         # Agent 引擎（planner/executor/reporter）
│   ├── rag/           # RAG 引擎（loader~retriever 13组件）
│   ├── mcp/           # MCP 6工具（AKShare+MongoDB）
│   ├── db/            # SQLite 业务数据库
│   ├── api/           # FastAPI 路由
│   ├── models/        # Pydantic 模型
│   ├── middleware/     # 鉴权限流
│   ├── utils/         # 重试/日志/监控/Redis
│   └── tests/         # 单元测试
├── frontend/          # Streamlit 前端
├── evaluation/        # 评测脚本+数据集+报告
├── docs/              # BRD+架构图
├── scripts/           # 运维脚本
└── data/              # 文档/向量库/模型
```

---

## 📝 文档

- [BRD 业务需求说明书](docs/BRD-业务需求说明书.md)
- [系统架构图](docs/架构图.md)
- [项目进度](PROGRESS.md)
