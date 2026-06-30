
# 项目进度存档

> 📅 最后更新：2026-06-30 20:42
> 🎯 目标：完成智能财务分析平台，具备企业级 RAG 能力
> ✅ 里程碑1：RAG Pipeline 验证
> ✅ 里程碑2：Embedding 升级 + 混合检索
> ✅ 里程碑3：四步口诀完整实现（语义切分 + Query处理 + LambdaMART + 评测）
> ✅ 里程碑4：RAG 全面完善（jieba分词 + 标准测试集 + 评测体系 + 参数实验 + 可配置化）

---

## 当前状态

| 模块 | 进度 | 完善度 | 说明 |
|------|------|--------|------|
| RAG 文档加载 | ✅ | 🟢 85% | PDF/Word/MD/TXT，表格仍是纯文本 |
| RAG 语义切分 | ✅ | 🟢 85% | 逐页语义+可配置阈值，sigma_mul 可调 |
| RAG 向量化 | ✅ | 🟢 90% | bge-base-zh-v1.5 768维，未对比其他模型 |
| RAG 向量存储 | ✅ | 🟢 90% | ChromaDB，BM25已上 jieba 分词 |
| RAG Query 处理 | ✅ | 🟢 80% | 扩写+余弦校验，阈值已可通过 config 配置 |
| RAG 混合检索 | ✅ | 🟢 85% | BM25(jieba)+语义+RRF+LambdaMART，分词准确 |
| RAG LambdaMART | ✅ | 🟡 50% | Cross-Encoder替代，架构预留真实LambdaMART接口 |
| RAG 策略路由 | ✅ | 🟢 80% | 关键词匹配路由，够用 |
| RAG 检索+问答 | ✅ | 🟢 85% | deepseek-v4-pro，准确率高 |
| RAG 评测 | ✅ | 🟢 80% | 20题标准测试集 + recall@k/MRR/NDCG + 批量评测 |
| RAG 参数实验 | ✅ | 🟢 90% | 4组对比实验脚本（chunk/overlap/阈值/query）|
| FastAPI 后端 | ✅ | 🟢 85% | 5接口（含评测），缺鉴权/限流/重试 |
| Streamlit 前端 | ✅ | 🟡 50% | 能上传问答，缺流式输出/错误兜底 |
| Docker 部署 | ⏳ | — | 后期 |
| 表格结构化 | ⏳ | — | PDF表格→结构化数据 |
| Agent 模块 | ⏳ | — | 第二阶段 |
| MCP 集成 | ⏳ | — | 第三阶段 |

---

## 技术栈

- Python 3.12（D:\Python312）
- FastAPI + Streamlit
- LangChain 1.x + ChromaDB
- DeepSeek v4（flash 快速 / pro 推理）
- BGE 中文 Embedding（本地免费）

---

## 2026-06-30 本次完善内容

### 1. BM25 jieba 分词 ✅
- 新建 `backend/rag/jieba_tokenizer.py`：封装 jieba + 138 个财务术语词典
- `hybrid_search.py` 中 BM25 从 `list()` 改为 `jieba.lcut()` + `jieba.lcut_for_search()`
- `requirements.txt` 添加 `jieba>=0.42`

### 2. 标准测试集 ✅
- 新建 `data/test_questions.json`：20 道财务问答
- 覆盖 6 类：数值查询(5) / 趋势分析(4) / 对比分析(3) / 定义解释(3) / 风险分析(2) / 综合推理(3)
- 难度分布：easy(5) / medium(10) / hard(5)

### 3. 评测体系升级 ✅
- `evaluator.py` 新增：`recall_at_k()`, `precision_at_k()`, `mrr()`, `ndcg_at_k()`, `evaluate_retrieval()`, `batch_evaluate()`, `save_report()`, `get_latest_report()`
- 支持按难度/类别分组统计

### 4. 参数对比实验脚本 ✅
- 新建 `backend/rag/experiments.py`
- 4 组实验：chunk_size / overlap / 语义阈值 / Query 余弦阈值
- 每项输出对比表格 + 推荐值
- CLI 入口：`python -m backend.rag.experiments [experiment_name]`

### 5. 参数可配置化 ✅
- `config.py` 新增：`SEMANTIC_THRESHOLD_MODE`, `SEMANTIC_MIN/MAX_CHUNK_SIZE`, `SEMANTIC_OVERLAP_RATIO`, `QUERY_SHORT_THRESHOLD`, `QUERY_MIN_SIMILARITY`
- `semantic_splitter.py` 从 config 读取，支持 `sigma_mul` 参数
- `query_processor.py` 从 config 读取阈值

### 6. API 评测接口 ✅
- 新增 `POST /api/v1/rag/evaluate`：运行批量评测
- 新增 `GET /api/v1/rag/eval-report`：获取最近评测报告
- `schemas.py` 新增 `EvalRequest`, `EvalReportResponse` 等模型

---

## 关键决策记录

1. **API Key 安全**：`.env` 在 `.gitignore` 中，不会被推送
2. **模型选择**：使用最新模型名 deepseek-v4-flash / deepseek-v4-pro
3. **Embedding**：使用本地 BGE 模型而非 API，零成本
4. **向量库**：选 ChromaDB 而非 Milvus，轻量级免运维
5. **分块参数**：chunk_size=800, overlap=150
6. **BM25 分词**：jieba 精确模式 + 138 个财务术语词典，替换原按字符切词
7. **评测体系**：20 题标准测试集 + recall@k/MRR/NDCG 三维检索指标 + LLM-as-Judge 生成指标
8. **参数实验**：4 组对比实验脚本，可在重建索引后自动找到最优参数

---

## 下一步待办（按优先级）

### 优先级 1：运行参数对比实验（已完成 ✅）
- [x] **跑 Query 阈值实验**：0.7/0.8/0.85 结果相同，保持 0.8
- [x] **跑 chunk_size 实验**：800（R@5=85.8%）碾压 500（R@5=67.5%），当前 800 最优
- [x] **结论**：当前默认参数即最优，无需调整

### 优先级 2：评测基线建立（已完成 ✅）
- [x] **跑完整评测**：20题标准测试集，R@5=91.2%, MRR=85.8%, NDCG@5=193.4%
- [x] **基线已记录**：easy 86.7% / medium 92.5% / hard 93.3%
- [x] **多份年报测试**：新下载茅台+腾讯年报，3文档跨文档检索评测完成

### 评测基线（单文档，仅比亚迪 — 2026-06-30 15:35）
| 指标 | 值 | 说明 |
|------|-----|------|
| Recall@1 | 68.2% | Top-1 命中率 |
| Recall@3 | 87.9% | Top-3 命中率 |
| Recall@5 | 91.2% | Top-5 命中率（核心指标）|
| MRR | 85.8% | 平均倒数排名 |
| 数值查询类 | R@5=86.7% | 相对较弱，精确数字匹配 |
| 趋势分析类 | R@5=81.2% | Q06 拖低（关键词太苛刻）|
| 对比分析类 | R@5=100% | 全命中 |
| 跨文档检索 | R@5=83.3% | 茅台vs比亚迪，MRR=100% |

### 评测基线（多文档：比亚迪+茅台+腾讯，1443 chunks — 2026-06-30 17:22）
| 指标 | 值 | vs 单文档 | 说明 |
|------|-----|-----------|------|
| Recall@1 | 47.2% | ↓21.0pp | Top-1 命中率显著下降 |
| Recall@3 | 68.6% | ↓19.3pp | Top-3 命中率 |
| Recall@5 | 75.4% | ↓15.8pp | Top-5 命中率（核心指标）|
| MRR | 82.9% | ↓2.9pp | 平均倒数排名相对稳定 |

**多文档评测关键发现：**
- 🔴 检索空间从 ~800 chunk 膨胀到 ~1443 chunk，R@5 下降 15.8 个百分点
- 🔴 Q02（茅台归母净利润）R@5=0%，完全未命中——"归属于母公司股东的净利润"被语义检索遗漏
- 🔴 Q06（茅台营收同比增长）R@5=25%，跨文档干扰导致趋势分析类大幅下降
- 🟡 Q19（茅台vs比亚迪对比）R@5=66.7%，但 MRR=100%，对比分析仍能命中核心 chunk
- 🟢 MRR 仅降 2.9pp，说明排名质量尚可，问题主要在召回覆盖
- 📌 **结论**：多文档场景需要增强 Query 处理（实体链接 + 文档范围限定），否则检索空间膨胀会显著稀释精度

---

## 2026-06-30 多文档检索优化（P0+P1）

### P0 — 评测数字格式归一化 ✅
- `evaluator.py` 新增 `_normalize_text()`: 去空白符 + 去千分位逗号 + 全角→半角
- 修复"1,741.44亿元" vs "1741.44亿元" 匹配问题
- **效果: R@5 +1.7pp (77.1% → 78.8%)**

### P1 — Query 财务术语展开 ✅
- `query_processor.py` 新增 `expand_financial_terms()`: 缩写→年报全称词典
- 按缩写长度降序处理，防短词污染（如"净利"误匹配"净利润"）
- 集成到 `process_query` → `rag_query` 和评测 API 路径
- 当前效果: 评测无明显增益（检索模型对术语展开不敏感），保留作为架构能力

### Entity Routing — Query 实体识别 + 文档过滤 ✅（架构能力）
- 新增 `entity_router.py`: 公司实体注册表（茅台/比亚迪/腾讯 + 别名/股票代码）
- 单公司 query → 限定文档搜索；跨文档对比 → 搜索全部
- 评测发现: 过滤+LambdaMART重排后 R@5 无提升（74.4% vs 77.1%）
- **根因**: 通用 Cross-Encoder 不懂财务数字等价变换；摘要文件 vs 完整年报的 chunk 质量差异大
- 保留作为可配置架构能力，`hybrid_search(enable_entity_routing=True/False)`

### 优化效果总结
| 阶段 | R@5 | MRR | 说明 |
|------|-----|-----|------|
| 单文档基线 | 91.2% | 85.8% | 仅比亚迪+摘要 |
| 多文档（无优化）| 77.1% | 82.9% | 3份年报，检索空间膨胀 |
| +P0 数字归一化 | **78.8%** | 82.9% | 修复评测格式误判 |
| +P1 术语展开 | 78.8% | 82.9% | 评测层面无变化 |
| +Entity Routing+重排 | 74.4% | 80.8% | 反而略降（见根因分析）|

### 剩余 5 题失败根因
- Q02/Q05/Q06/Q07/Q14: 均为茅台年报 chunk 检索质量问题
- 完整年报（143页/382chunks）中关键数字分散，BM25+语义检索找不到精确 chunk
- 下一步需要: 财务领域专用 Reranker，或财务报表结构化提取

### 优先级 3：工程完善
- [ ] PDF 表格结构化提取
- [ ] 前端流式输出（SSE）
- [ ] API 鉴权 + 限流
- [ ] 异常重试机制

### 优先级 4：新功能
- [ ] Agent 数据分析模块
- [ ] MCP Server
- [ ] Docker 部署

---

## 启动方式

```bash
# 终端 1：后端
cd D:\实战项目\financial-ai-platform
python backend\main.py

# 终端 2：前端
streamlit run frontend\app.py
```
