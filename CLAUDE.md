# 智能财务分析平台 — 项目专属约束

## 进度追踪

1. **每完成一个独立功能点，立即 commit + push**（commit message 用中文描述本次改动）
2. **每次进度变更后，更新 `PROGRESS.md`**（记录日期、改动内容、评测数据）
3. **每次进度变更后，同步更新 `D:\个人资料\面试准备-项目深挖点.md`**（新增知识点、面试深挖问答、失败教训）

## 评测纪律

1. 修改 RAG pipeline（loader/splitter/retriever/hybrid_search/evaluator）后，**必须跑 23 题评测**验证基线
2. 评测结果如实记录到 PROGRESS.md，**不准选择性汇报**（提升的记、下降的也要记）
3. 当前评测基线：**23 题 R@5=85.1%，MRR=89.2%**——任何改动后与此对比

## 安全红线

1. `.env` 文件绝对不提交（已在 `.gitignore` 中）
2. API Key 不出现在代码中，始终从环境变量读取
3. 面试准备文件（`D:\个人资料\面试准备-项目深挖点.md`）不在项目目录内，不随 git 推送

## 技术约定

1. Python 解释器路径：`D:/Python312/python.exe`
2. 模型缓存全部指向 D 盘，不占 C 盘
3. 新增依赖先加到 `requirements.txt`，安装后再改代码
4. 索引重建脚本：`python scripts/rebuild_index.py`
5. 所有配置通过 `backend/config.py` + `.env` 管理，不硬编码

## 项目结构速查

```
financial-ai-platform/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 全局配置
│   ├── api/rag.py           # RAG API（上传/问答/评测）
│   ├── models/schemas.py    # Pydantic 数据模型
│   └── rag/
│       ├── loader.py        # 文档加载（PDF/Word/MD/TXT + 表格提取）
│       ├── semantic_splitter.py  # 语义动态切分 + 大表格注入
│       ├── embedder.py      # BGE Embedding 模型
│       ├── vector_store.py  # ChromaDB 管理
│       ├── hybrid_search.py # 混合检索（BM25+语义+RRF+LambdaMART）
│       ├── query_processor.py    # Query 处理（术语展开+扩写+校验）
│       ├── entity_router.py      # 实体识别+文档路由
│       ├── jieba_tokenizer.py    # 中文分词+财务词典
│       ├── evaluator.py     # 评测体系（R@k/MRR/NDCG+数字归一化）
│       ├── model_router.py  # LLM 调用路由
│       └── retriever.py     # 完整 RAG 问答入口
├── evaluation/
│   ├── rag/quick_eval.py     # RAG 50题全量评测
│   ├── agent/bench_agent.py  # Agent 子任务拆解评测
│   ├── bench_speed.py        # 检索速度基准
│   ├── data/                 # 评测数据集
│   │   ├── rag_questions.json
│   │   └── agent_questions.json
│   └── reports/              # 评测报告输出
├── data/
│   ├── documents/           # 原始文档（年报PDF/摘要MD）
│   ├── chroma_db/           # ChromaDB 持久化
│   └── models/              # 本地 Embedding/Reranker 模型
├── logs/                    # 应用日志（JSON轮转）
├── scripts/rebuild_index.py # 一键重建向量索引
├── scripts/run_tests.py     # 测试运行器
└── PROGRESS.md              # 项目进度存档
```
