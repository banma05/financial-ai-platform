"""
智能财务分析平台 - Streamlit 前端
"""
import streamlit as st
import requests

# ============ 页面配置 ============
st.set_page_config(
    page_title="智能财务分析平台",
    page_icon="📊",
    layout="wide",
)

# API 地址
API_BASE = "http://localhost:8000/api/v1/rag"

# ============ 侧边栏 ============
with st.sidebar:
    st.title("📊 智能财务分析平台")
    st.markdown("---")
    menu = st.radio(
        "导航",
        ["💬 知识库问答", "📁 文档管理"],
    )
    st.markdown("---")
    st.caption("基于 RAG 的财务报告智能分析系统")
    st.caption("Powered by DeepSeek + ChromaDB")

# ============ 知识库问答页面 ============
if menu == "💬 知识库问答":
    st.title("💬 财务知识库问答")

    # 状态提示
    docs_resp = requests.get(f"{API_BASE}/documents")
    if docs_resp.status_code == 200:
        doc_count = docs_resp.json().get("total", 0)
        if doc_count == 0:
            st.warning("⚠️ 知识库中没有文档，请先在「文档管理」页面上传文件")
        else:
            st.success(f"✅ 知识库已就绪，共 {doc_count} 个文档")

    # 聊天输入
    query = st.text_area(
        "请输入你的问题",
        placeholder="例如：该公司2024年的毛利率是多少？与去年相比有什么变化？",
        height=100,
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        search_btn = st.button("🔍 搜索", type="primary", use_container_width=True)
    with col2:
        top_k = st.slider("检索文档数", min_value=1, max_value=10, value=5)

    if search_btn and query.strip():
        with st.spinner("🔍 正在检索相关文档..."):
            try:
                resp = requests.post(
                    f"{API_BASE}/chat",
                    json={"query": query.strip(), "top_k": top_k},
                    timeout=60,
                )
                if resp.status_code == 200:
                    data = resp.json()

                    # 显示答案
                    st.markdown("### 📝 回答")
                    st.markdown(data["answer"])

                    # 显示处理时间
                    st.caption(f"⏱️ 处理耗时：{data['processing_time']} 秒")

                    # 显示来源
                    if data.get("sources"):
                        st.markdown("---")
                        st.markdown("### 📚 参考来源")
                        for i, src in enumerate(data["sources"], 1):
                            with st.expander(
                                f"来源 {i}：{src['source']}（第 {src['page']} 页，相似度 {src['score']}）"
                            ):
                                st.text(src["content"])
                else:
                    st.error(f"请求失败：{resp.text}")
            except requests.exceptions.ConnectionError:
                st.error("❌ 无法连接到后端服务，请先启动后端：`python backend/main.py`")
            except Exception as e:
                st.error(f"❌ 出错了：{e}")

# ============ 文档管理页面 ============
elif menu == "📁 文档管理":
    st.title("📁 文档管理")

    # 上传区域
    st.markdown("### 📤 上传文档")
    st.caption("支持格式：PDF / Word / Markdown / TXT（最大 50MB）")

    uploaded_file = st.file_uploader(
        "选择文件",
        type=["pdf", "docx", "doc", "md", "txt"],
        label_visibility="collapsed",
    )

    if uploaded_file:
        with st.spinner("📄 正在处理文档..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                resp = requests.post(f"{API_BASE}/upload", files=files, timeout=120)
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(f"✅ {data['message']}")
                    st.info(f"文件名：{data['filename']} | 大小：{data['file_size'] / 1024:.1f}KB | 文本块：{data['chunk_count']}")
                else:
                    st.error(f"上传失败：{resp.json().get('detail', resp.text)}")
            except requests.exceptions.ConnectionError:
                st.error("❌ 无法连接到后端服务")
            except Exception as e:
                st.error(f"❌ 出错了：{e}")

    # 已上传文档列表
    st.markdown("---")
    st.markdown("### 📋 知识库文档列表")

    if st.button("🔄 刷新"):
        st.rerun()

    try:
        resp = requests.get(f"{API_BASE}/documents", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data["total"] == 0:
                st.info("知识库为空，请上传文档")
            else:
                for doc in data["documents"]:
                    with st.container():
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.text(f"📄 {doc['filename']}")
                        with col2:
                            st.text(f"📊 {doc['page_count']} 页")
                        with col3:
                            st.text(f"🧩 {doc['chunk_count']} 块")
                        st.divider()
    except Exception:
        st.error("无法获取文档列表")
