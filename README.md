
# 📊 智能财务分析平台

> 三模块 AI 财务分析系统：RAG 知识库 + Agent 分析 + MCP 数据源

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.138-green)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1.3-orange)](https://www.langchain.com/)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-purple)](https://langchain-ai.github.io/langgraph/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek_v4-purple)](https://www.deepseek.com/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-brightgreen)](https://www.trychroma.com/)
[![AKShare](https://img.shields.io/badge/Data-AKShare-red)](https://akshare.akfamily.xyz/)

---

## 🎯 项目定位

**NL → 检索 → 分析 → 报告** 全流程自动化。覆盖"查数据 → 算指标 → 画图表 → 写报告"完整链路。

| 模块 | 功能 | 核心指标 | 状态 |
|------|------|------|:--:|
| **一 RAG** | 财报/公告/研报 智能问答+溯源 | SEM-R@5=95.2%, GPU 3.8x | ✅ |
| **二 Agent** | NL需求 → 多步推理 → 分析报告 | LangGraph DAG, 5模板, 19公式, 152测试 | ✅ |
| **三 MCP** | 外部金融数据源（6工具） | AKShare 真实行情+财报, 22测试 | ✅ |

---

## 🏗️ 技术架构

```
┌───────────────────────────────────────────────────────────┐
│                    Streamlit 前端                           │
│     RAG 智能问答  │  Agent 数据分析  │  MCP 工具调用         │
└────────────────────────┬──────────────────────────────────┘
                         │ HTTP/SSE
┌────────────────────────▼──────────────────────────────────┐
│                  FastAPI 后端 + 鉴权限流                     │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌─────────┐  │
│  │ RAG API  │  │Agent API │  │ MCP API   │  │文档管理  │  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └─────────┘  │
└───────┼──────────────┼──────────────┼─────────────────────┘
        │              │              │
┌───────▼──────────────▼──────────────▼─────────────────────┐
│                    核心引擎层                                │
│                                                             │
│  ┌───────────────── RAG 引擎 ────────────────────┐         │
│  │ Query理解 → BM25+语义双路 → RRF → LambdaMART │         │
│  │ BGE Embedding(GPU) + CrossEncoder(GPU)        │         │
│  │ 50题双轨评测(SEM-R@5=95.2%) + 4066 chunks     │         │
│  └───────────────────────────────────────────────┘         │
│                                                             │
│  ┌───────────────── Agent 引擎 ───────────────────┐        │
│  │ Planner(LLM拆解+5模板) → Executor(DAG并行)     │        │
│  │ → Reporter(Markdown报告)                       │        │
│  │ LangGraph StateGraph + ThreadPoolExecutor       │        │
│  │ ParamInjector三层注入 + tenacity重试 + trace_id │        │
│  └───────────────────────────────────────────────┘        │
│                                                             │
│  ┌───────────────── MCP 工具 ─────────────────────┐        │
│  │ stock_price │ financial_statements │ ratios    │        │
│  │ industry_compare │ market_index │ calendar     │        │
│  │ AKShare(新浪)实时数据 + Mock兜底                │        │
│  └───────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- NVIDIA GPU（可选，CPU 也可运行但慢 ~4x）
- DeepSeek API Key（[申请地址](https://platform.deepseek.com)）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY
```

### 3. 启动

```bash
# 终端 1：后端
python backend/main.py

# 终端 2：前端
streamlit run frontend/app.py
```

打开 http://localhost:8501，即可使用完整三模块功能。

---

## 📂 项目结构

```
financial-ai-platform/
├── backend/
│   ├── rag/                    # 模块一：RAG 知识库
│   │   ├── loader.py            文档加载（PDF/Word/MD/TXT + 表格提取）
│   │   ├── semantic_splitter.py  语义动态切分
│   │   ├── embedder.py           BGE 向量化（GPU加速）
│   │   ├── hybrid_search.py      混合检索（BM25+语义→RRF→LambdaMART）
│   │   ├── query_processor.py    Query理解（术语展开+LLM扩写）
│   │   ├── evaluator.py          评测体系（50题+R@k/MRR/NDCG）
│   │   ├── retriever.py          完整RAG问答入口
│   │   └── model_router.py       LLM统一调用（flash/pro分层）
│   │
│   ├── agent/                  # 模块二：Agent 分析
│   │   ├── graph.py              LangGraph StateGraph 编排
│   │   ├── planner.py            任务拆解 + 5模板
│   │   ├── executor.py           ToolRegistry + 依赖注入
│   │   ├── reporter.py           报告生成
│   │   └── tools/                工具包
│   │       ├── data_query.py       RAG检索→结构化提取
│   │       ├── financial_calc.py   19财务公式（7大类）
│   │       ├── chart.py            5种图表
│   │       └── param_injection.py  三层回退依赖注入
│   │
│   ├── mcp/                    # 模块三：MCP 工具
│   │   ├── mock_data.py           AKShare 数据提供器
│   │   ├── server.py              独立Server预留
│   │   └── tools/                 6个MCP工具
│   │
│   ├── utils/                  # 公共工具
│   │   ├── retry.py               tenacity重试+CircuitBreaker
│   │   └── logger.py              结构化日志（trace_id+JSON轮转）
│   │
│   ├── api/                    # FastAPI 路由
│   ├── middleware/              # 鉴权限流
│   ├── tests/                  # 152 单元测试
│   ├── config.py
│   └── main.py
│
├── evaluation/                 # 评测脚本+数据集+报告
│   ├── rag/quick_eval.py        50题双轨评测
│   ├── agent/bench_agent.py     Agent拆解评测
│   └── data/                    评测数据集
│
├── frontend/app.py             # Streamlit 前端
├── data/                       # 运行时数据
│   ├── documents/               9份原始文档
│   ├── chroma_db/               ChromaDB持久化
│   └── models/                  本地Embedding模型
│
├── scripts/                    # 运维脚本
│   ├── run_tests.py
│   └── rebuild_index.py
│
├── requirements.txt
└── PROGRESS.md
```

---

## 📊 评测基线

| 场景 | KW-R@5 | SEM-R@5 | MRR | 文档数 | Chunks |
|------|:------:|:-------:|:---:|:------:|:------:|
| 当前（9文档, mean-1std） | 70.7% | **95.2%** | 89.2% | 9 | 4066 |
| 旧（3文档, mean-0.5std） | 87.3% | — | 90.8% | 3 | 2882 |

| Agent 指标 | 状态 |
|-----------|:--:|
| 财务公式计算准确率 | ✅ 19公式/40测试 |
| Agent单元测试 | ✅ 152全过 |
| 子任务拆解准确率 | 76.9%（目标≥85%） |

---

## 🔑 核心亮点

1. **混合检索 + GPU全链路**：BM25+语义双路 → RRF → LambdaMART(CrossEncoder GPU) + BGE Embedding GPU，单题2.6s
2. **LangGraph DAG 并行**：StateGraph 顶层编排 + ThreadPoolExecutor 层内并行，8任务3层并行执行
3. **三层依赖注入**：精确映射(60对) → 编辑距离模糊匹配 → LLM语义匹配，命中率可统计
4. **AKShare 真实数据**：6个MCP工具，新浪/巨潮实时行情+财务报表，Mock兜底
5. **全链路可追溯**：trace_id 贯穿 Planner→Executor→Reporter，JSON按天轮转日志
6. **引用溯源**：每个回答追溯源文件+页码，满足合规审计

---

## 🗺️ 路线图

| 阶段 | 内容 | 状态 |
|------|------|:--:|
| 一 | Bug修复 + LangGraph重构 | ✅ |
| 二 | 依赖注入 + 重试 + 结构化日志 | ✅ |
| 三 | MCP 6工具 + AKShare真实数据 | ✅ |
| 四 | Docker + Redis + CI/CD + 集成测试 | ✅ |
| 五 | 三模块联动 + 统一评测 | ⏳ |

---

## 👤 作者

AI 专业 × 会计辅修，专注 AI 在财务场景的落地应用。
