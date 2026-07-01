"""
智能财务分析平台 — Streamlit 前端
三模块架构：知识库 RAG / 数据分析 Agent / MCP 工具
"""
import streamlit as st
import requests
import json
import time

# ============ 页面配置 ============
st.set_page_config(
    page_title="智能财务分析平台",
    page_icon="📊",
    layout="wide",
)

# API 地址
API_BASE = "http://localhost:8000/api/v1/rag"

# ============ 会话状态初始化 ============
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # [{role, content, sources?, time?}]
if "max_retries" not in st.session_state:
    st.session_state.max_retries = 2


def check_backend() -> bool:
    """检查后端是否存活"""
    try:
        r = requests.get("http://localhost:8000/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def sse_chat(query: str, top_k: int = 5):
    """
    流式调用后端 SSE 接口，逐 token yield。
    Yields: {"type":"token","content":"..."} | {"type":"done","sources":[...],...} | {"type":"error","message":"..."}
    """
    try:
        resp = requests.post(
            f"{API_BASE}/chat/stream",
            json={"query": query, "top_k": top_k},
            stream=True,
            timeout=120,
        )
        if resp.status_code != 200:
            yield {"type": "error", "message": f"请求失败 ({resp.status_code}): {resp.text}"}
            return

        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                data_str = line[6:]
                try:
                    yield json.loads(data_str)
                except json.JSONDecodeError:
                    continue

    except requests.exceptions.ConnectionError:
        yield {"type": "error", "message": "无法连接到后端服务，请先启动后端：`python backend/main.py`"}
    except Exception as e:
        yield {"type": "error", "message": f"请求异常：{e}"}


# ============ 侧边栏 ============
with st.sidebar:
    st.title("📊 智能财务分析平台")
    st.markdown("---")

    # 三模块导航
    menu = st.radio(
        "导航",
        [
            "💬 知识库问答",
            "🤖 数据分析 Agent",
            "🔧 MCP 工具集成",
            "📁 文档管理",
        ],
    )

    st.markdown("---")

    # 后端状态
    backend_ok = check_backend()
    if backend_ok:
        st.success("🟢 后端服务运行中")
    else:
        st.error("🔴 后端服务未启动")

    st.markdown("---")
    st.caption("智能财务分析平台 V1.0")
    st.caption("知识库 + Agent + MCP 三模块架构")
    st.caption("Powered by DeepSeek + ChromaDB + BGE")

# ============ 知识库问答 ============
if menu == "💬 知识库问答":
    st.title("💬 财务知识库问答")
    st.caption("基于 RAG 检索增强生成，上传年报/公告/研报后自然语言提问，AI 基于文档回答并溯源")

    # 知识库状态
    col_status, col_clear = st.columns([3, 1])
    with col_status:
        try:
            docs_resp = requests.get(f"{API_BASE}/documents", timeout=5)
            if docs_resp.status_code == 200:
                doc_count = docs_resp.json().get("total", 0)
                if doc_count == 0:
                    st.warning("⚠️ 知识库中没有文档，请先在「文档管理」页面上传文件")
                else:
                    st.success(f"✅ 知识库就绪 — {doc_count} 个文档")
        except Exception:
            st.warning("⚠️ 无法获取知识库状态")
    with col_clear:
        if st.button("🗑️ 清空对话", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

    st.markdown("---")

    # 聊天历史
    chat_container = st.container()
    with chat_container:
        for i, msg in enumerate(st.session_state.chat_history):
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(msg["content"])
            else:
                with st.chat_message("assistant"):
                    st.markdown(msg["content"])
                    if msg.get("sources"):
                        with st.expander(f"📚 参考来源（{len(msg['sources'])} 条）"):
                            for j, src in enumerate(msg["sources"], 1):
                                st.caption(f"**来源 {j}**：{src['source']}（第 {src['page']} 页 · 相似度 {src['score']:.3f}）")
                                st.text(src["content"][:300] + ("..." if len(src.get("content", "")) > 300 else ""))
                                st.divider()
                    if msg.get("time"):
                        st.caption(f"⏱️ {msg['time']} 秒")

    # 输入区域
    st.markdown("---")
    col_input, col_btn, col_k = st.columns([5, 1, 1])
    with col_input:
        query = st.chat_input(
            placeholder="输入你的财务问题，例如：比亚迪2024年毛利率是多少？与2023年相比变化的原因？",
        )
    with col_k:
        top_k = st.selectbox("检索数", [3, 5, 7, 10], index=1, key="top_k_select")

    if query:
        # 添加用户消息
        st.session_state.chat_history.append({"role": "user", "content": query})

        # 流式获取答案
        with st.chat_message("assistant"):
            answer_placeholder = st.empty()
            sources_placeholder = st.empty()
            time_placeholder = st.empty()

            full_answer = ""
            sources = []
            proc_time = 0

            for event in sse_chat(query, top_k=top_k):
                if event["type"] == "token":
                    full_answer += event["content"]
                    answer_placeholder.markdown(full_answer + "▌")

                elif event["type"] == "done":
                    answer_placeholder.markdown(full_answer)
                    sources = event.get("sources", [])
                    proc_time = event.get("processing_time", 0)

                    if sources:
                        with sources_placeholder.expander(f"📚 参考来源（{len(sources)} 条）"):
                            for j, src in enumerate(sources, 1):
                                st.caption(f"**来源 {j}**：{src['source']}（第 {src['page']} 页 · 相似度 {src['score']:.3f}）")
                                st.text(src["content"][:300] + ("..." if len(src.get("content", "")) > 300 else ""))
                                st.divider()

                    time_placeholder.caption(f"⏱️ 耗时 {proc_time} 秒")

                elif event["type"] == "error":
                    answer_placeholder.error(f"❌ {event['message']}")

            # 保存到历史
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": full_answer or "(未获取到回答)",
                "sources": sources,
                "time": proc_time,
            })

        st.rerun()

# ============ 数据分析 Agent（占位）============
elif menu == "🤖 数据分析 Agent":
    st.title("🤖 数据分析 Agent")
    st.caption("自然语言驱动数据查询、分析和报告生成")

    st.info("""
    ### 🚧 模块二：规划中

    **核心能力（即将开发）：**

    - **NL 驱动数据查询**：用自然语言提问，Agent 自动从知识库和外部数据源提取数据
    - **自动分析报告**：生成包含"数据→图表→结论→建议"的专业财务分析报告
    - **可视化图表**：自动生成折线图、柱状图、饼图、雷达图
    - **多步推理**：复杂分析问题自动拆解为子任务，逐步执行
    - **分析模板**：杜邦分析、现金流分析、盈利能力评估等预设模板

    **预计启动**：模块一工程化完成后
    """)

    # 预留演示界面
    st.markdown("---")
    st.subheader("🔮 效果预览")
    st.markdown("""
    > **用户**：对比茅台和比亚迪近三年毛利率趋势，分析差异原因，生成图表

    > **Agent**：
    > 1. 检索茅台 2022-2024 年毛利率 → 92.0% → 91.8% → 92.2%
    > 2. 检索比亚迪 2022-2024 年毛利率 → 15.9% → 18.2% → 19.4%
    > 3. 计算趋势：茅台稳定高位，比亚迪持续提升
    > 4. 差异分析：商业模式差异（高端品牌 vs 规模制造）
    > 5. 📈 生成对比折线图
    > 6. 📝 生成分析报告...
    """)

# ============ MCP 工具集成（占位）============
elif menu == "🔧 MCP 工具集成":
    st.title("🔧 MCP 工具集成")
    st.caption("为 Agent 提供外部金融数据调用能力")

    st.info("""
    ### 🚧 模块三：规划中

    **核心工具（即将开发）：**

    | 工具 | 功能 | 状态 |
    |------|------|:----:|
    | Wind 数据接口 | 股票行情、财务数据、宏观指标 | ⏳ |
    | 同花顺数据接口 | 实时行情、历史数据、板块数据 | ⏳ |
    | 财务公式计算器 | 杜邦分析、现金流折现、比率分析等 | ⏳ |
    | 行业对标工具 | 同行业可比公司数据对标 | ⏳ |

    **预计启动**：模块二完成后
    """)

    # 展示已内置的财务公式
    st.markdown("---")
    st.subheader("🧮 已规划财务公式库（可离线使用）")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**盈利能力**")
        st.caption("毛利率 = (营收-成本)/营收")
        st.caption("净利率 = 净利润/营收")
        st.caption("ROE = 净利润/净资产")
        st.caption("ROA = 净利润/总资产")

    with col2:
        st.markdown("**偿债能力**")
        st.caption("流动比率 = 流动资产/流动负债")
        st.caption("速动比率 = (流动资产-存货)/流动负债")
        st.caption("资产负债率 = 总负债/总资产")

    with col3:
        st.markdown("**估值指标**")
        st.caption("PE = 股价/每股收益")
        st.caption("PB = 股价/每股净资产")
        st.caption("股息率 = 每股分红/股价")

# ============ 文档管理 ============
elif menu == "📁 文档管理":
    st.title("📁 文档管理")

    # 上传区域
    st.markdown("### 📤 上传文档")
    st.caption("支持格式：PDF / Word / Markdown / TXT（最大 50MB）")
    st.caption("适用文档：企业年报、临时公告、券商研报等中文财务文件")

    uploaded_file = st.file_uploader(
        "选择文件",
        type=["pdf", "docx", "doc", "md", "txt"],
        label_visibility="collapsed",
    )

    if uploaded_file:
        with st.spinner("📄 正在解析文档并构建向量索引..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                resp = requests.post(f"{API_BASE}/upload", files=files, timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(f"✅ {data['message']}")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("文件名", data["filename"])
                    with col2:
                        st.metric("文件大小", f"{data['file_size'] / 1024:.1f} KB")
                    with col3:
                        st.metric("文本块数", data["chunk_count"])
                    st.info("💡 文档已就绪，切换到「知识库问答」页面开始提问")
                else:
                    detail = resp.json().get("detail", resp.text)
                    st.error(f"上传失败：{detail}")
            except requests.exceptions.ConnectionError:
                st.error("❌ 无法连接到后端服务，请先启动后端：`python backend/main.py`")
            except requests.exceptions.ReadTimeout:
                st.error("❌ 上传超时，文件可能过大或后端处理太慢，请重试")
            except Exception as e:
                st.error(f"❌ 出错了：{e}")

    # 已上传文档列表
    st.markdown("---")
    col_title, col_refresh = st.columns([3, 1])
    with col_title:
        st.markdown("### 📋 知识库文档列表")
    with col_refresh:
        if st.button("🔄 刷新列表", use_container_width=True):
            st.rerun()

    try:
        resp = requests.get(f"{API_BASE}/documents", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data["total"] == 0:
                st.info("知识库为空，请上传文档开始使用")
            else:
                st.caption(f"共 {data['total']} 个文档")
                for doc in data["documents"]:
                    with st.container():
                        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                        with col1:
                            st.markdown(f"📄 **{doc['filename']}**")
                        with col2:
                            st.caption(f"📊 {doc['page_count']} 页")
                        with col3:
                            st.caption(f"🧩 {doc['chunk_count']} 块")
                        with col4:
                            st.caption(f"📅 {doc.get('created_at', '-')[:10] if doc.get('created_at') else '-'}")
                        st.divider()
        else:
            st.error(f"获取文档列表失败：HTTP {resp.status_code}")
    except requests.exceptions.ConnectionError:
        st.warning("⚠️ 后端服务未启动，无法获取文档列表")
    except Exception as e:
        st.error(f"获取文档列表出错：{e}")
