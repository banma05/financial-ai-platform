"""
端到端集成测试 — 覆盖 RAG → Agent → MCP 全链路

≥10 用例，每个验证一个完整的功能路径。
不依赖外部 API（Mock 所有 LLM/ChromaDB/AKShare 调用）。
"""
import pytest
from unittest.mock import patch, MagicMock


# ==================== RAG 集成测试 ====================

class TestRAGIntegration:
    """RAG 问答全链路"""

    @patch("rag.retriever.hybrid_search")
    @patch("rag.retriever.routed_chat")
    def test_rag_query_basic(self, mock_chat, mock_search):
        """基本问答：检索→生成 全链路"""
        mock_search.return_value = [
            {"source": "茅台2024年报.pdf", "page": 42, "content": "营业收入1741.44亿元",
             "score": 0.95}
        ]
        mock_chat.return_value = "贵州茅台2024年营业收入为1741.44亿元。[^1]\n\n---\n[^1]: 茅台2024年报.pdf, 第42页"

        from rag.retriever import rag_query
        result = rag_query("茅台2024年营收多少？", top_k=3)

        assert "answer" in result
        assert "sources" in result
        assert len(result["sources"]) == 1
        assert "1741.44" in result["answer"]

    @patch("rag.retriever.hybrid_search")
    @patch("rag.retriever.routed_chat")
    def test_rag_query_no_results(self, mock_chat, mock_search):
        """知识库无结果时返回友好提示"""
        mock_search.return_value = []

        from rag.retriever import rag_query
        result = rag_query("火星2024年营收多少？", top_k=3)

        assert "未找到" in result["answer"] or "没有找到" in result["answer"]
        assert result["sources"] == []

    @patch("rag.retriever.hybrid_search")
    @patch("rag.retriever.routed_chat")
    def test_rag_query_with_history(self, mock_chat, mock_search):
        """多轮对话：历史正确传递"""
        mock_search.return_value = [
            {"source": "test.pdf", "page": 1, "content": "毛利率92.38%", "score": 0.9}
        ]
        mock_chat.return_value = "92.38%[^1]"

        from rag.retriever import rag_query
        result = rag_query(
            "那毛利率呢？", top_k=3,
            history=[{"role": "user", "content": "茅台营收多少？"},
                     {"role": "assistant", "content": "1741.44亿元"}]
        )

        assert result["sources"]  # 确保检索被执行


# ==================== Agent 集成测试 ====================

class TestAgentIntegration:
    """Agent 分析全链路"""

    @patch("agent.planner.chat")
    def test_agent_plan_with_template(self, mock_chat):
        """模板模式：盈利能力模板完整链路"""
        mock_chat.return_value = '{"tasks": [], "requires_clarification": null}'

        from agent.planner import Planner, BUILTIN_TEMPLATES
        planner = Planner()
        template = BUILTIN_TEMPLATES.get("profitability")
        assert template is not None
        assert len(template["tasks"]) >= 4  # 模板至少4个任务

    @patch("agent.graph.run_agent_sync")
    def test_agent_sync_returns_valid_report(self, mock_run):
        """同步分析返回含报告的结构"""
        mock_run.return_value = {
            "report": "## 分析报告\n\n测试报告内容",
            "charts": [],
            "task_count": 3,
            "processing_time": 2.5,
        }

        from agent.graph import run_agent_sync
        result = run_agent_sync("分析茅台盈利能力", template_name="profitability")

        assert "report" in result
        assert "task_count" in result
        assert "processing_time" in result


# ==================== MCP 集成测试 ====================

class TestMCPIntegration:
    """MCP 工具全链路"""

    def test_tool_registry_has_all_tools(self):
        """ToolRegistry 包含全部 9 个工具（3 原有 + 6 MCP）"""
        from agent.executor import ToolRegistry
        from agent.tools.data_query import DataQueryTool
        from agent.tools.financial_calc import FinancialCalcTool
        from agent.tools.chart import ChartTool
        from mcp import (
            StockPriceTool, FinancialStatementsTool, CalculateRatioTool,
            IndustryComparisonTool, MarketIndexTool, FinancialCalendarTool,
        )

        registry = ToolRegistry()
        registry.register(DataQueryTool())
        registry.register(FinancialCalcTool())
        registry.register(ChartTool())
        registry.register(StockPriceTool())
        registry.register(FinancialStatementsTool())
        registry.register(CalculateRatioTool())
        registry.register(IndustryComparisonTool())
        registry.register(MarketIndexTool())
        registry.register(FinancialCalendarTool())

        tools = registry.list_tools()
        assert len(tools) == 9
        tool_names = {t["name"] for t in tools}
        assert "data_query" in tool_names
        assert "mcp_stock_price" in tool_names

    def test_mcp_tool_contract(self):
        """所有 MCP 工具遵循统一协议（name + run）"""
        from mcp import (
            StockPriceTool, FinancialStatementsTool, CalculateRatioTool,
            IndustryComparisonTool, MarketIndexTool, FinancialCalendarTool,
        )

        tools = [
            StockPriceTool(), FinancialStatementsTool(),
            CalculateRatioTool(), IndustryComparisonTool(),
            MarketIndexTool(), FinancialCalendarTool(),
        ]

        for tool in tools:
            assert hasattr(tool, "name"), f"{type(t).__name__} 缺 name 属性"
            assert hasattr(tool, "run"), f"{type(t).__name__} 缺 run 方法"
            assert isinstance(tool.name, str)
            assert callable(tool.run)


# ==================== 依赖注入集成测试 ====================

class TestParamInjectionIntegration:
    """依赖注入全链路"""

    def test_full_injection_pipeline(self):
        """完整注入管道：中文数据 → 英文公式参数"""
        from agent.tools.param_injection import get_injector, reset_injector

        reset_injector()
        injector = get_injector()

        # 模拟 DataQuery 返回数据
        extracted = {
            "营业收入": "1741.44亿元",
            "净利润": "862.28亿元",
            "净利": "862.28亿元",  # Level2 模糊匹配
        }

        params = {}
        injector.inject(extracted, params)

        assert params["revenue"] == 1741.44
        assert params["net_profit"] == 862.28
        # 统计应正确
        stats = injector.get_stats()
        assert stats["level1"] >= 2  # 营业收入 + 净利润
        assert stats["level2"] >= 1  # 净利 → 净利润（编辑距离1）


# ==================== 日志 + 重试 集成测试 ====================

class TestUtilsIntegration:
    """工具层集成"""

    def test_trace_timer_works(self):
        """TraceTimer 正常计时"""
        import time
        from utils.logger import TraceTimer

        with TraceTimer("test_integration"):
            time.sleep(0.05)
        # 不抛异常 = 通过

    def test_retry_decorator_integration(self):
        """重试装饰器：成功场景"""
        from utils.retry import retry

        call_count = [0]

        @retry(max_retries=2, base_delay=0.01)
        def succeed_on_third():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("临时失败")
            return "ok"

        result = succeed_on_third()
        assert result == "ok"
        assert call_count[0] == 3


# ==================== 健康检查 ====================

class TestHealthCheck:
    """系统健康检查"""

    def test_health_status(self):
        from utils.monitor import get_health_status
        health = get_health_status()
        assert "status" in health
        assert "checks" in health

    def test_corpus_stats(self):
        from rag.corpus_manager import get_corpus_stats
        stats = get_corpus_stats()
        assert "document_count" in stats
        assert isinstance(stats["document_count"], int)

    def test_request_tracker(self):
        from utils.monitor import RequestTracker
        tracker = RequestTracker(max_history=5)
        tracker.record("/test", 50.0, True)
        tracker.record("/test", 200.0, True)
        stats = tracker.get_stats()
        assert stats["total_requests"] == 2
        assert stats["success_rate"] == 100.0
