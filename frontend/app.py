"""
智能财务分析平台 — Streamlit 前端
三模块架构：知识库 RAG / 数据分析 Agent / MCP 工具
"""
import streamlit as st
import requests
import json
import time
from loguru import logger

# ============ 页面配置 ============
st.set_page_config(
    page_title="智能财务分析平台",
    page_icon="📊",
    layout="wide",
)

# API 地址
API_BASE = "http://localhost:8001/api/v1/rag"
AGENT_API_BASE = "http://localhost:8001/api/v1/agent"

# ============ 会话状态初始化 ============
CACHE_TTL = 30

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "session_id" not in st.session_state:
    import uuid
    st.session_state.session_id = str(uuid.uuid4())[:8]  # 8位随机会话ID
if "backend_ok" not in st.session_state:
    st.session_state.backend_ok = None
if "doc_count" not in st.session_state:
    st.session_state.doc_count = None
if "last_api_check" not in st.session_state:
    st.session_state.last_api_check = 0
if "agent_history" not in st.session_state:
    st.session_state.agent_history = []
if "agent_session_id" not in st.session_state:
    import uuid
    st.session_state.agent_session_id = str(uuid.uuid4())[:8]


def _cache_expired() -> bool:
    """缓存是否过期"""
    return (time.time() - st.session_state.last_api_check) > CACHE_TTL


def refresh_backend_status():
    """刷新后端状态和文档计数（带缓存，避免每次渲染都请求）"""
    now = time.time()
    if not _cache_expired() and st.session_state.backend_ok is not None:
        return  # 缓存未过期，跳过
    try:
        r = requests.get("http://localhost:8001/health", timeout=3)
        st.session_state.backend_ok = r.status_code == 200
        if st.session_state.backend_ok:
            try:
                docs_resp = requests.get(f"{API_BASE}/documents", timeout=5)
                if docs_resp.status_code == 200:
                    st.session_state.doc_count = docs_resp.json().get("total", 0)
            except Exception as e:
                logger.debug(f"获取文档列表失败: {e}")
    except Exception as e:
        logger.debug(f"后端状态检查失败: {e}")
        st.session_state.backend_ok = False
    st.session_state.last_api_check = now


def sse_chat(query: str, top_k: int = 5):
    """
    流式调用后端 SSE 接口，逐 token yield。
    Yields: {"type":"token","content":"..."} | {"type":"done","sources":[...],...} | {"type":"error","message":"..."}
    """
    try:
        resp = requests.post(
            f"{API_BASE}/chat/stream",
            json={"query": query, "top_k": top_k, "session_id": st.session_state.session_id},
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


def sse_agent_analyze(query: str, template: str = None):
    """
    SSE 调用 Agent 分析接口，逐事件 yield。

    Yields: plan_start / task_start / task_complete / chart / report_start / done / error / clarification
    """
    try:
        payload = {"query": query, "session_id": st.session_state.get("agent_session_id", "default"), "template": template}
        resp = requests.post(
            f"{AGENT_API_BASE}/analyze/stream",
            json=payload,
            stream=True,
            timeout=300,
        )
        if resp.status_code != 200:
            yield {"type": "error", "message": f"请求失败 ({resp.status_code}): {resp.text}"}
            return

        for line in resp.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                try:
                    yield json.loads(line[6:])
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

    # 后端状态（带缓存，不卡页面切换）
    refresh_backend_status()
    if st.session_state.backend_ok:
        with st.expander("🟢 后端运行中", expanded=False):
            st.caption(f"文档数：{st.session_state.doc_count if st.session_state.doc_count is not None else '?'}")
            if st.button("🔄 强制刷新状态", use_container_width=True):
                st.session_state.last_api_check = 0
                st.rerun()
    elif st.session_state.backend_ok is False:
        st.error("🔴 后端未启动")
    else:
        st.warning("⏳ 检查中...")

    st.markdown("---")
    st.caption("智能财务分析平台 V1.0")
    st.caption("知识库 + Agent + MCP 三模块架构")
    st.caption("Powered by DeepSeek + ChromaDB + BGE")

# ============ 知识库问答 ============
if menu == "💬 知识库问答":
    st.title("💬 财务知识库问答")
    st.caption("基于 RAG 检索增强生成，上传年报/公告/研报后自然语言提问，AI 基于文档回答并溯源")

    # 知识库状态（从缓存读取，不卡切换）
    col_status, col_clear = st.columns([3, 1])
    with col_status:
        doc_count = st.session_state.doc_count
        if doc_count is None:
            st.warning("⏳ 正在检查知识库...")
        elif doc_count == 0:
            st.warning("⚠️ 知识库中没有文档，请先在「文档管理」页面上传文件")
        else:
            st.success(f"✅ 知识库就绪 — {doc_count} 个文档")
    with col_clear:
        if st.button("🗑️ 清空对话", use_container_width=True):
            st.session_state.chat_history = []
            # 同时清除后端会话历史
            try:
                requests.post(
                    f"{API_BASE}/session/clear",
                    params={"session_id": st.session_state.session_id},
                    timeout=3,
                )
            except Exception as e:
                logger.debug(f"清空会话失败: {e}")
            # 生成新的会话ID（避免旧历史残留）
            import uuid
            st.session_state.session_id = str(uuid.uuid4())[:8]
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

# ============ 数据分析 Agent ============
elif menu == "🤖 数据分析 Agent":
    st.title("🤖 数据分析 Agent")
    st.caption("自然语言驱动数据查询、指标计算、图表生成和报告撰写")

    # 展示历史分析
    for i, item in enumerate(st.session_state.agent_history):
        with st.chat_message("user"):
            st.markdown(f"**分析需求**：{item['query']}")
            if item.get("template"):
                st.caption(f"📋 模板：{item['template']}")
        with st.chat_message("assistant"):
            if item.get("clarification"):
                st.warning(f"⚠️ {item['clarification']}")
            else:
                st.markdown(item.get("report", ""))
                if item.get("charts"):
                    for idx, chart_b64 in enumerate(item["charts"], 1):
                        st.image(f"data:image/png;base64,{chart_b64}", caption=f"图表 {idx}")
                st.caption(f"⏱️ {item.get('time', 0):.1f} 秒 | 子任务 {item.get('task_count', 0)} 个")

    # 输入区域
    with st.container():
        st.markdown("---")
        col1, col2 = st.columns([4, 1])
        with col1:
            analysis_query = st.text_area(
                "输入分析需求",
                placeholder=(
                    "例1：对比茅台和比亚迪近三年毛利率趋势，分析差异原因\n"
                    "例2：帮我做一份茅台2024年的杜邦分析\n"
                    "例3：分析腾讯的现金流健康状况"
                ),
                height=90,
                key="agent_input",
            )
        with col2:
            template = st.selectbox(
                "分析模板",
                ["无（自由分析）", "盈利能力评估", "杜邦分析", "成长性分析", "现金流分析", "财务风险扫描"],
                key="agent_template",
            )
            submitted = st.button("🚀 开始分析", use_container_width=True, type="primary")

    if submitted and analysis_query:
        # 映射模板名
        template_map = {
            "盈利能力评估": "profitability",
            "杜邦分析": "dupont",
            "成长性分析": "growth",
            "现金流分析": "cash_flow",
            "财务风险扫描": "risk_scan",
        }
        template_name = template_map.get(template, None)

        st.session_state.agent_history.append({
            "query": analysis_query,
            "template": template if template != "无（自由分析）" else None,
        })
        current_idx = len(st.session_state.agent_history) - 1

        # 进度展示区
        status_container = st.empty()
        progress_bar = st.progress(0, text="🚀 正在规划分析任务...")
        report_container = st.empty()
        chart_container = st.empty()

        # 调用 SSE 流式接口
        full_report = ""
        charts = []
        task_count = 0
        processing_time = 0

        for event in sse_agent_analyze(analysis_query, template_name):
            etype = event.get("type", "")

            if etype == "clarification":
                status_container.warning(f"⚠️ {event.get('question', '需要更多信息')}")
                st.session_state.agent_history[current_idx]["clarification"] = event.get("question")
                progress_bar.empty()

            elif etype == "plan_start":
                task_count = event.get("task_count", 0)
                progress_bar.progress(0.05, text=f"📋 已规划 {task_count} 个子任务，开始执行...")

            elif etype == "task_start":
                tid = event.get("task_id", "?")
                desc = event.get("description", "")
                t_idx = event.get("task_idx", 0)
                total = event.get("total", 1)
                progress = 0.05 + 0.75 * (t_idx / max(total, 1))
                progress_bar.progress(progress, text=f"🔄 [{tid}/{total}] {desc}")

            elif etype == "task_complete":
                status = "✅" if event.get("success") else "❌"
                summary = event.get("summary", "")
                if summary:
                    status_container.info(f"{status} {summary}")

            elif etype == "chart":
                chart_b64 = event.get("chart_base64", "")
                if chart_b64:
                    charts.append(chart_b64)
                    chart_container.image(f"data:image/png;base64,{chart_b64}",
                                          caption=f"图表 {event.get('chart_index', len(charts))}")

            elif etype == "report_start":
                progress_bar.progress(0.85, text="📝 正在生成分析报告...")

            elif etype == "done":
                progress_bar.progress(1.0, text="✅ 分析完成!")
                full_report = event.get("report", "")
                processing_time = event.get("processing_time", 0)

                # 更新已有的图表展示
                if charts:
                    with chart_container.container():
                        for idx, chart_b64 in enumerate(charts, 1):
                            st.image(f"data:image/png;base64,{chart_b64}", caption=f"图表 {idx}")

                report_container.markdown(full_report)
                status_container.success(f"⏱️ 分析完成，耗时 {processing_time:.1f} 秒，共执行 {task_count} 个子任务")

            elif etype == "error":
                status_container.error(f"❌ {event.get('message', '分析出错')}")
                progress_bar.empty()

        # 更新历史记录
        st.session_state.agent_history[current_idx].update({
            "report": full_report,
            "charts": charts,
            "task_count": task_count,
            "time": processing_time,
        })

        # 清除历史按钮
        if st.button("🗑️ 清除分析历史"):
            st.session_state.agent_history = []
            st.rerun()

# ============ MCP 工具集成（占位）============
elif menu == "🔧 MCP 工具集成":
    st.title("🔧 MCP 工具集成")
    st.caption("外部金融数据源接入 — Mock 数据演示（真 API 预留接口）")

    tool_map = {
        "mcp_stock_price": "股票行情",
        "mcp_financial_statements": "财务报表",
        "mcp_calculate_ratio": "财务比率",
        "mcp_industry_comparison": "行业对比",
        "mcp_market_index": "大盘指数",
        "mcp_financial_calendar": "财报日历",
    }

    tool_choice = st.selectbox(
        "选择 MCP 工具", list(tool_map.keys()),
        format_func=lambda x: f"{tool_map[x]} ({x})"
    )

    symbol = st.text_input("股票代码", "600519",
                           help="600519=贵州茅台 / 002594=比亚迪 / 00700=腾讯")

    if st.button("🚀 调用工具", type="primary"):
        try:
            from mcp import (
                StockPriceTool, FinancialStatementsTool, CalculateRatioTool,
                IndustryComparisonTool, MarketIndexTool, FinancialCalendarTool,
            )
            tools = {
                "mcp_stock_price": StockPriceTool(),
                "mcp_financial_statements": FinancialStatementsTool(),
                "mcp_calculate_ratio": CalculateRatioTool(),
                "mcp_industry_comparison": IndustryComparisonTool(),
                "mcp_market_index": MarketIndexTool(),
                "mcp_financial_calendar": FinancialCalendarTool(),
            }
            tool = tools[tool_choice]

            with st.spinner(f"调用 {tool_map[tool_choice]}..."):
                result = tool.run(symbol=symbol)

            if result.get("success"):
                st.success(f"✅ {result.get('summary', '调用成功')}")
                with st.expander("📊 查看完整数据", expanded=True):
                    st.json(result)
            else:
                st.error(f"❌ {result.get('error', '调用失败')}")
        except Exception as e:
            st.error(f"工具调用异常: {e}")

    # 工具列表参考
    with st.expander("📋 所有 MCP 工具一览", expanded=False):
        st.markdown("""
        | 工具 | 功能 | 数据来源 |
        |------|------|:------:|
        | stock_price | 实时行情/历史K线 | Mock（茅台/比亚迪/腾讯） |
        | financial_statements | 利润表/资产负债表/现金流 | Mock（2024年报数据） |
        | calculate_ratio | 批量计算15个财务比率 | Mock + financial_calc 公式库 |
        | industry_comparison | 同行业 5 家公司对比 | Mock（白酒/新能源/互联网） |
        | market_index | 上证/沪深300/行业指数 | Mock |
        | financial_calendar | 财报披露日/分红/股东会 | Mock（2026年真实日期） |
        """)

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
                    # 上传成功后刷新缓存
                    st.session_state.last_api_check = 0
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
                            st.caption(f"📊 {doc.get('page_count', 0)} 页")
                        with col3:
                            st.caption(f"🧩 {doc.get('chunk_count', 0)} 块")
                        with col4:
                            upload_time = doc.get('upload_time', '')
                            st.caption(f"📅 {upload_time[:10] if upload_time else '-'}")
                        st.divider()
        else:
            st.error(f"获取文档列表失败：HTTP {resp.status_code}")
    except requests.exceptions.ConnectionError:
        st.warning("⚠️ 后端服务未启动，无法获取文档列表")
    except Exception as e:
        st.error(f"获取文档列表出错：{e}")

    # ── 知识库统计面板 ──
    st.markdown("---")
    st.markdown("### 📊 知识库统计")
    try:
        resp = requests.get(f"{API_BASE.replace('/api/v1/rag', '')}/api/v1/admin/stats/corpus", timeout=10)
        if resp.status_code == 200:
            stats = resp.json()
            if "error" not in stats:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📚 文档数", stats.get("document_count", "?"))
                with col2:
                    st.metric("🧩 总Chunks", stats.get("total_chunks", "?"))
                with col3:
                    st.metric("💾 总大小", f"{stats.get('total_size_mb', '?')}MB")
                with col4:
                    st.metric("🕐 最近更新", stats.get("last_modified", "?")[:10] if stats.get("last_modified") else "?")

                # 文件类型分布
                if stats.get("by_type"):
                    types = ", ".join(f"{k}({v})" for k, v in stats["by_type"].items())
                    st.caption(f"文件类型: {types}")

                # 质量检查
                resp2 = requests.get(f"{API_BASE.replace('/api/v1/rag', '')}/api/v1/admin/corpus/validate", timeout=10)
                if resp2.status_code == 200:
                    quality = resp2.json()
                    if quality.get("is_healthy"):
                        st.success(f"✅ 质量检查通过 — {quality.get('summary', '')}")
                    else:
                        st.warning(f"⚠️ {quality.get('summary', '')}")
                        for issue in quality.get("issues", []):
                            st.error(f"❌ {issue['file']}: {issue['issue']}")
    except Exception as e:
        logger.debug(f"知识库统计获取失败: {e}")

    # ── 系统健康 + 监控 ──
    st.markdown("---")
    st.markdown("### 🩺 系统健康 + 请求监控")

    try:
        # 健康检查
        resp = requests.get(f"{API_BASE.replace('/api/v1/rag', '')}/api/v1/admin/health", timeout=5)
        if resp.status_code == 200:
            health = resp.json()
            status_icon = "✅" if health.get("status") == "healthy" else "⚠️"
            st.caption(f"{status_icon} 系统状态: **{health.get('status', '?')}** | "
                       f"GPU: {'✅' if health.get('checks', {}).get('gpu', {}).get('available') else '❌'} | "
                       f"ChromaDB: {'✅' if health.get('checks', {}).get('chromadb', {}).get('status') == 'connected' else '❌'} | "
                       f"AKShare: {'✅' if health.get('checks', {}).get('akshare', {}).get('status') == 'available' else '❌'}")

        # 请求统计
        resp = requests.get(f"{API_BASE.replace('/api/v1/rag', '')}/api/v1/admin/stats/monitor", timeout=5)
        if resp.status_code == 200:
            mon = resp.json()
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📨 请求总数", mon.get("total_requests", 0))
            with col2:
                st.metric("✅ 成功率", f"{mon.get('success_rate', 100)}%")
            with col3:
                st.metric("⏱ P95延迟", f"{mon.get('latency_p95_ms', 0)}ms")
            with col4:
                uptime = mon.get("uptime_readable", "?")
                st.metric("🕐 运行时间", uptime)

            # 告警
            alerts = mon.get("alerts", [])
            if alerts:
                st.warning(f"🚨 {len(alerts)} 个告警")
                for a in alerts:
                    st.error(f"[{a['level'].upper()}] {a['message']}")

            # 端点统计
            if mon.get("endpoints"):
                with st.expander("📋 端点统计详情"):
                    for ep, s in mon["endpoints"].items():
                        st.caption(f"**{ep}**: {s['count']}次 | "
                                   f"平均{s['avg_latency_ms']}ms | 错误率{s['error_rate']}%")
    except Exception as e:
        logger.debug(f"系统监控数据获取失败: {e}")
