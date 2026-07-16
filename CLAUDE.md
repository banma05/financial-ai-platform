# 智能财务分析平台 — 项目专属约束

## 进度追踪

1. **每完成一个独立功能点，立即 commit + push**（commit message 用中文描述本次改动）
2. **每次进度变更后，更新 `PROGRESS.md`**（记录日期、改动内容、评测数据）
3. **每次进度变更后，同步更新 `D:\个人资料\面试准备-项目深挖点.md`**

## 评测纪律

1. 每次重大改动后跑端到端评测验证
2. 评测结果如实记录，不准选择性汇报
3. 当前评测基线：**V8.2（Agent 97.0% | RAG 89.3% | 385+19+301测试全绿）**

## 安全红线

1. `.env` 文件绝对不提交
2. API Key 不出现在代码中，始终从环境变量读取
3. 面试准备文件不在项目目录内，不随 git 推送

## 技术约定

1. Python 虚拟环境：`D:/实战项目/.venv/Scripts/python.exe` (Python 3.12.10)
2. 模型缓存指向：`D:/Python312/huggingface-cache`
3. 新增依赖先加到 `requirements.txt`，安装后再改代码
4. 所有配置通过 `backend/config.py` + `.env` 管理，不硬编码
5. LLM：DeepSeek v4-flash（简单）+ v4-pro（复杂）
6. Embedding：BAAI/bge-base-zh-v1.5（768维，本地）
7. Reranker：BAAI/bge-reranker-v2-m3（本地）

## V8.0 架构速查

```
Planner(LLM) → Executor(线性) → Reporter(LLM) → 报告+图表
                    │
          ┌────────┼────────┐
          ▼        ▼        ▼
       SQL查    RAG辅助   公式计算+图表
      (毫秒级)  (文字解读)  (Python零LLM)
```

## 目录结构速查

```
backend/
├── main.py                  # FastAPI 入口
├── config.py                # 全局配置
├── agent/                   # Agent（LangGraph 三节点）
│   ├── graph.py, planner.py, executor.py, reporter.py, schemas.py
│   └── tools/               # data_query, financial_calc, chart, param_injection
├── rag/                     # RAG 引擎
│   ├── loader.py, semantic_splitter.py, embedder.py, vector_store.py
│   ├── hybrid_search.py, query_processor.py, entity_router.py
│   ├── jieba_tokenizer.py, evaluator.py, model_router.py, retriever.py
│   ├── keywords.py, corpus_manager.py
├── mcp/                     # MCP 6工具（datasource.py + tools/）
├── db/                      # SQLite 业务库
├── api/                     # FastAPI 路由（rag + agent）
├── models/                  # Pydantic 数据模型
├── middleware/               # 鉴权+限流
├── utils/                   # retry, logger, monitor, redis_client
└── tests/                   # 单元测试
```

## 启动

```bash
cd D:\实战项目\financial-ai-platform

# 后端 :8001
source ../.venv/Scripts/activate
python backend/main.py

# 前端 :5173（开发模式，自动代理 /api → :8001）
cd web
npx vite
```
