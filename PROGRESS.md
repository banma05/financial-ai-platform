
# 项目进度存档

> 📅 最后更新：2026-06-29 23:45
> 🎯 目标：完成智能财务分析平台，具备企业级 RAG 能力
> ✅ 里程碑1：RAG Pipeline 验证
> ✅ 里程碑2：Embedding 升级 + 混合检索
> ✅ 里程碑3：四步口诀完整实现（语义切分 + Query处理 + LambdaMART + 评测）

---

## 当前状态

| 模块 | 进度 | 说明 |
|------|------|------|
| RAG 文档加载 | ✅ 完成 | 支持 PDF/Word/MD/TXT |
| RAG 语义切分 | ✅ 完成 | 逐页语义切分，15%重叠，保留页码（290页→767块） |
| RAG 混合检索 | ✅ 完成 | BM25 + 语义 → RRF 融合（~0.5s），复杂才走 LambdaMART |
| RAG LambdaMART | ✅ 完成 | Cross-Encoder 统一打分，按需启用 |
| RAG 评测 | ✅ 完成 | LLM-as-Judge 上下文召回率+忠实度 |
| RAG 向量化 | ✅ 完成 | bge-base-zh-v1.5 768维 |
| RAG 向量存储 | ✅ 完成 | ChromaDB |
| RAG Query 处理 | ✅ 完成 | 短句扩写 + 余弦校验 >0.8 |
| RAG 混合检索 | ✅ 完成 | BM25 + 语义 + RRF 融合 |
| RAG LambdaMART | ✅ 完成 | Cross-Encoder 统一打分（0.99+） |
| RAG 策略路由 | ✅ 完成 | simple→向量 / complex→混合+重排 |
| RAG 检索 + 问答 | ✅ 完成 | deepseek-v4-pro |
| RAG 评测 | ✅ 完成 | 上下文召回率 + 忠实度双标拆分 |
| FastAPI 后端 | ✅ 完成 | 3 个接口已就绪 |
| Streamlit 前端 | ✅ 完成 | 上传 + 问答界面 |
| Docker 部署 | ⏳ 未开始 | 后期再做 |
| 文档表格解析 | ⏳ 未开始 | 财务 PDF 表格结构化提取 |
| Agent 模块 | ⏳ 未开始 | 第二阶段开发 |
| MCP 集成 | ⏳ 未开始 | 第三阶段 |

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

## 下一步待办

### 优先级 1（本周）
- [ ] 下载 2-3 份真实上市公司年报 PDF
- [ ] 跑通完整流程：上传 → 问答 → 验证
- [ ] 记录 bad case，优化检索策略

### 优先级 2（后续）
- [ ] 财务 PDF 表格结构化解析
- [ ] 混合检索（关键词 + 语义）
- [ ] 重排序（Reranker）接入
- [ ] 批量化测试集构建

### 优先级 3（Agent 阶段）
- [ ] 数据分析 Agent 模块
- [ ] MCP Server 开发
- [ ] Docker 容器化

---

## 启动方式

```bash
# 终端 1：后端
cd D:\实战项目\financial-ai-platform
python backend\main.py

# 终端 2：前端
streamlit run frontend\app.py
```
