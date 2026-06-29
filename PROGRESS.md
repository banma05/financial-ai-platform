
# 项目进度存档

> 📅 最后更新：2026-06-30 00:10
> 🎯 目标：完成智能财务分析平台，具备企业级 RAG 能力
> ✅ 里程碑1：RAG Pipeline 验证
> ✅ 里程碑2：Embedding 升级 + 混合检索
> ✅ 里程碑3：四步口诀完整实现（语义切分 + Query处理 + LambdaMART + 评测）

---

## 当前状态

| 模块 | 进度 | 完善度 | 说明 |
|------|------|--------|------|
| RAG 文档加载 | ✅ | 🟢 85% | PDF/Word/MD/TXT，表格仍是纯文本 |
| RAG 语义切分 | ✅ | 🟡 70% | 逐页语义+15%重叠，阈值未做对比调优 |
| RAG 向量化 | ✅ | 🟢 90% | bge-base-zh-v1.5 768维，未对比其他模型 |
| RAG 向量存储 | ✅ | 🟢 80% | ChromaDB，BM25分词未上jieba |
| RAG Query 处理 | ✅ | 🟡 60% | 扩写阈值15字、余弦0.8 均为经验值 |
| RAG 混合检索 | ✅ | 🟡 65% | BM25+语义+RRF，分词粗糙 |
| RAG LambdaMART | ✅ | 🔴 40% | Cross-Encoder替代，无真实LambdaMART训练 |
| RAG 策略路由 | ✅ | 🟢 80% | 关键词匹配路由，够用 |
| RAG 检索+问答 | ✅ | 🟢 85% | deepseek-v4-pro，准确率高 |
| RAG 评测 | ✅ | 🔴 30% | LLM-as-Judge可跑，无标准测试集 |
| FastAPI 后端 | ✅ | 🟢 80% | 3接口，缺鉴权/限流/重试 |
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

## 关键决策记录

1. **API Key 安全**：`.env` 在 `.gitignore` 中，不会被推送
2. **模型选择**：使用最新模型名 deepseek-v4-flash / deepseek-v4-pro
3. **Embedding**：使用本地 BGE 模型而非 API，零成本
4. **向量库**：选 ChromaDB 而非 Milvus，轻量级免运维
5. **分块参数**：chunk_size=800, overlap=150

---

## 下一步待办（按优先级）

### 优先级 1：参数对比实验（明天先做）
- [ ] **chunk_size 对比**：200-1200 / 300-800 / 500-1000，10题测召回率
- [ ] **overlap 对比**：10% / 15% / 20%，同上
- [ ] **语义阈值对比**：均值-1σ / 均值-0.5σ / 均值（当前 -0.5σ）
- [ ] **Query余弦阈值**：0.7 / 0.8 / 0.85，测扩写噪声率

### 优先级 2：检索质量优化
- [ ] **BM25 上 jieba 分词**：替换按字符切词，精度预期 +10-20%
- [ ] **多份年报测试**：再下载 2-3 份年报，验证跨文档检索
- [ ] **构造标准测试集**：20 题 + 人工标注答案页码，可复现评测

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
