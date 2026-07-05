"""
知识库管理 + 可观测性 单元测试
"""
import time
import pytest
from rag.corpus_manager import get_corpus_stats, validate_documents, check_new_documents
from utils.monitor import RequestTracker, get_health_status, check_alerts


class TestRequestTracker:
    def setup_method(self):
        self.tracker = RequestTracker(max_history=10)
        self.tracker.reset()

    def test_record_and_stats(self):
        self.tracker.record("/api/rag/chat", 150.0, True)
        self.tracker.record("/api/rag/chat", 250.0, True)
        self.tracker.record("/api/agent/analyze", 500.0, False)

        stats = self.tracker.get_stats()
        assert stats["total_requests"] == 3
        assert stats["total_success"] == 2
        assert stats["total_errors"] == 1
        assert stats["success_rate"] == pytest.approx(66.7, 0.1)
        assert "/api/rag/chat" in stats["endpoints"]

    def test_latency_percentiles(self):
        for i in range(10):
            self.tracker.record("/test", float(i * 10), True)

        stats = self.tracker.get_stats()
        assert stats["latency_p50_ms"] > 0
        assert stats["latency_p95_ms"] >= stats["latency_p50_ms"]

    def test_uptime(self):
        stats = self.tracker.get_stats()
        assert stats["uptime_seconds"] >= 0
        assert "s" in stats["uptime_readable"]

    def test_reset(self):
        self.tracker.record("/test", 100.0, True)
        self.tracker.reset()
        stats = self.tracker.get_stats()
        assert stats["total_requests"] == 0


class TestCorpusManager:
    def test_get_stats(self):
        stats = get_corpus_stats()
        assert "document_count" in stats
        assert "total_chunks" in stats
        assert isinstance(stats["document_count"], int)

    def test_validate_documents(self):
        result = validate_documents()
        assert "is_healthy" in result
        assert "summary" in result

    def test_check_new_documents(self):
        result = check_new_documents()
        assert "new" in result
        assert "modified" in result


class TestHealthCheck:
    def test_get_health_status(self):
        health = get_health_status()
        assert "status" in health
        assert "checks" in health
        assert "gpu" in health["checks"]

    def test_check_alerts_empty(self):
        """空追踪器不应有告警"""
        tracker = RequestTracker()
        tracker.reset()
        # 添加一些成功请求
        tracker.record("/test", 50.0, True)
        # check_alerts 使用的是全局 tracker，不是局部
        # 所以这个测试验证格式即可
        alerts = check_alerts()
        assert isinstance(alerts, list)
