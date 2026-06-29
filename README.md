# 📊 智能财务分析平台

> 基于 RAG（检索增强生成）的企业级财务报告智能问答系统

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.138-green)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1.3-orange)](https://www.langchain.com/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-purple)](https://www.deepseek.com/)
[![ChromaDB](https://img.shields.io/badge/VectorDB-ChromaDB-brightgreen)](https://www.trychroma.com/)

---

## 🎯 项目定位

**面向企业内部财务团队 / 金融分析师的 AI 知识库工具**，解决财务报告阅读效率低、信息查找慢的痛点。

| 痛点 | AI 方案 |
|------|---------|
| 翻阅几百页年报找 1 个数据 | 自然语言提问，秒级定位 |
| 跨多份报告人工比对数据 | AI 自动检索 + 对比分析 |
| 非财务人员读不懂报表术语 | AI 给出专业解释 + 上下文 |

> ⚠️ 这不是 Demo，而是按企业级标准设计的可落地项目。参考了[大模型应用开发学习路线](https://github.com)和真实招聘需求中要求的 RAG 完整能力。

---

## 🏗️ 技术架构

```
┌──────────────────────────────────────────────────────────┐
│                      用户界面层                            │
│            Streamlit 前端（文档上传 + 问答对话）              │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP API
┌──────────────────────▼───────────────────────────────────┐
│                    FastAPI 后端服务                        │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │ 文档上传 API │  │  知识库问答   │  │  文档管理 API   │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────┘  │
└─────────┼────────────────┼──────────────────────────────┘
          │                │
┌─────────▼────────────────▼──────────────────────────────┐
│                    RAG 引擎层                              │
│  ┌──────────┐  ┌───────────┐  ┌───────────────────────┐ │
│  │ 文档加载  │  │ 文本分块   │  │ 向量化（BGE 中文模型） │ │
│  │ PDF/Word │  │ 财务优化   │  │ 本地免费 Embedding    │ │
│  └────┬─────┘  └─────┬─────┘  └───────────┬───────────┘ │
│       └──────────────┴─────────────────────┘             │
│                          │                                │
│               ┌──────────▼──────────┐                    │
│               │   ChromaDB 向量库    │                    │
│               │   持久化存储 + 检索   │                    │
│               └──────────┬──────────┘                    │
│                          │                                │
│               ┌──────────▼──────────┐                    │
│               │   混合检索管道       │                    │
│               │  语义搜索 + 重排序   │                    │
│               └──────────┬──────────┘                    │
└──────────────────────────┼───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│                    模型路由层                              │
│  ┌────────────────┐         ┌──────────────────────┐     │
│  │ DeepSeek V3     │         │ DeepSeek R1          │     │
│  │ 文档摘要/分类    │         │ 复杂财务推理/多步分析  │     │
│  │ 快速响应        │         │ 深度推理             │     │
│  └────────────────┘         └──────────────────────┘     │
└──────────────────────────────────────────────────────────┘
```

### 模型路由策略

采用**多模型分层调用**，在成本和效果之间取得平衡：

| 任务类型 | 使用模型 | 原因 |
|----------|----------|------|
| 文档摘要 / 信息抽取 | `deepseek-chat` | 成本低速度快，适合简单任务 |
| 关键词提取 / 文本分类 | `deepseek-chat` | 无需深度推理 |
| 财务指标分析 / 趋势判断 | `deepseek-reasoner` | 需要多步推理 |
| 跨文档对比分析 / 异常检测 | `deepseek-reasoner` | 复杂逻辑链条 |
| 文本向量化 | 本地 BGE 模型 | 免费，无需 API 调用 |

> 这种设计在面试中可以展开讲：为什么做模型路由、如何判断任务复杂度、成本如何优化。

---

## 🚀 快速开始

### 环境要求

- Python 3.12+
- DeepSeek API Key（[申请地址](https://platform.deepseek.com)）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key
```

### 3. 启动后端

```bash
cd backend
python main.py
```

访问 http://localhost:8000/docs 查看 API 文档。

### 4. 启动前端

```bash
streamlit run frontend/app.py
```

浏览器打开后，上传财务文档，即可开始智能问答。

---

## 📡 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/rag/upload` | 上传文档（PDF/Word/MD/TXT） |
| `POST` | `/api/v1/rag/chat` | 向知识库提问 |
| `GET` | `/api/v1/rag/documents` | 查看知识库文档列表 |

### 示例：上传文档

```bash
curl -X POST http://localhost:8000/api/v1/rag/upload \
  -F "file=@茅台2024年报.pdf"
```

### 示例：提问

```bash
curl -X POST http://localhost:8000/api/v1/rag/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "2024年毛利率同比变化是多少？原因是什么？"}'
```

响应包含 AI 回答 + 引用来源（文件名、页码、相似度分数）。

---

## 📂 项目结构

```
financial-ai-platform/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 全局配置
│   ├── api/
│   │   └── rag.py            # RAG API 路由
│   ├── models/
│   │   └── schemas.py       # Pydantic 数据模型
│   └── rag/
│       ├── loader.py        # 多格式文档加载器
│       ├── splitter.py      # 财务文档专用分块器
│       ├── embedder.py      # BGE 向量化（本地免费）
│       ├── vector_store.py  # ChromaDB 管理
│       └── retriever.py     # 检索管道 + LLM 调用
├── frontend/
│   └── app.py               # Streamlit 界面
├── data/
│   ├── documents/           # 上传文档存储
│   └── chroma_db/           # 向量库持久化
├── requirements.txt
└── .env.example
```

---

## 🔑 核心技术亮点

### 1. 财务文档专用分块策略
针对财务报表表格密集、合并单元格多的特点，定制了分块参数（chunk_size=800, overlap=150），避免数值被拦腰截断。

### 2. 混合检索 + 重排序
语义搜索保证召回，关键词搜索保证精确匹配（如股票代码），重排序提升 Top-K 精度。

### 3. 引用溯源
每个回答都追溯到源文件的具体页码，满足企业合规审计要求。

### 4. 模型路由
简单任务走廉价模型（节省成本），复杂分析走推理模型（保证效果），按需调度。

### 5. 本地 Embedding
使用 BAAI/bge-small-zh-v1.5 本地向量化，中文效果好、零 API 成本、数据不出本地。

---

## 🗺️ 后续规划（见 Roadmap）

- [ ] 用户认证与多租户隔离
- [ ] 财务表格结构识别（PDF 表格 → 结构化数据）
- [ ] 多轮对话记忆 + 追问澄清
- [ ] Agent 模块：自主数据分析与报告生成
- [ ] MCP Server 集成：对接 Wind/同花顺等金融数据 API
- [ ] Docker 一键部署
- [ ] 评测体系：RAG 召回率、答案准确率量化评估

---

## 👤 作者

- AI 专业 x 会计辅修，专注 AI 在财务场景的落地应用
- 项目持续迭代中，欢迎 Star ⭐ 和 Issue

---

## 📄 License

MIT License