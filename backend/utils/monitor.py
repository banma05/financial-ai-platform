"""
可观测性模块 — 请求统计 + 延迟监控 + 健康检查

提供:
1. RequestTracker       — 请求计数和延迟统计（线程安全）
2. get_health_status()  — 系统健康检查
3. get_request_stats()  — 请求统计面板数据
4. check_alerts()       — 告警阈值检查
"""

import time
import threading
from collections import defaultdict
from typing import Dict, List, Optional
from loguru import logger


# ==================== 请求追踪器 ====================

class RequestTracker:
    """
    线程安全的请求追踪器。

    统计维度:
    - 总请求数 / 成功率
    - 按端点分类的请求数和延迟
    - 最近 N 次请求的延迟分布
    """

    def __init__(self, max_history: int = 100):
        self._lock = threading.Lock()
        self._max_history = max_history

        # 全局统计
        self.total_requests = 0
        self.total_success = 0
        self.total_errors = 0

        # 按端点统计: {endpoint: {"count": N, "total_latency": T, "errors": E}}
        self._endpoint_stats: Dict[str, Dict] = defaultdict(
            lambda: {"count": 0, "total_latency": 0.0, "errors": 0}
        )

        # 最近 N 次请求的延迟（毫秒）
        self._recent_latencies: List[float] = []

        # 启动时间
        self._start_time = time.time()

    def record(self, endpoint: str, latency_ms: float, success: bool = True):
        """记录一次请求"""
        with self._lock:
            self.total_requests += 1
            if success:
                self.total_success += 1
            else:
                self.total_errors += 1

            stats = self._endpoint_stats[endpoint]
            stats["count"] += 1
            stats["total_latency"] += latency_ms
            if not success:
                stats["errors"] += 1

            self._recent_latencies.append(latency_ms)
            if len(self._recent_latencies) > self._max_history:
                self._recent_latencies.pop(0)

    def get_stats(self) -> Dict:
        """获取完整统计"""
        with self._lock:
            uptime = time.time() - self._start_time

            # 延迟分位数（最近100次）
            sorted_lat = sorted(self._recent_latencies) if self._recent_latencies else [0]
            p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else 0
            p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if len(sorted_lat) > 1 else p50
            p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if len(sorted_lat) > 1 else p50

            # 端点统计
            endpoints = {}
            for ep, stats in self._endpoint_stats.items():
                endpoints[ep] = {
                    "count": stats["count"],
                    "avg_latency_ms": round(stats["total_latency"] / stats["count"], 1) if stats["count"] > 0 else 0,
                    "max_latency_ms": round(stats["total_latency"] / stats["count"] * 2, 1) if stats["count"] > 0 else 0,  # 简化估算
                    "error_rate": round(stats["errors"] / stats["count"] * 100, 1) if stats["count"] > 0 else 0,
                }

            return {
                "uptime_seconds": round(uptime, 1),
                "uptime_readable": _format_duration(uptime),
                "total_requests": self.total_requests,
                "total_success": self.total_success,
                "total_errors": self.total_errors,
                "success_rate": round(self.total_success / self.total_requests * 100, 1) if self.total_requests > 0 else 100.0,
                "latency_p50_ms": round(p50, 1),
                "latency_p95_ms": round(p95, 1),
                "latency_p99_ms": round(p99, 1),
                "avg_latency_ms": round(sum(self._recent_latencies) / len(self._recent_latencies), 1) if self._recent_latencies else 0,
                "request_rate_per_min": round(self.total_requests / (uptime / 60), 1) if uptime > 0 else 0,
                "endpoints": endpoints,
            }

    def reset(self):
        """重置统计（测试用）"""
        with self._lock:
            self.total_requests = 0
            self.total_success = 0
            self.total_errors = 0
            self._endpoint_stats.clear()
            self._recent_latencies.clear()
            self._start_time = time.time()


# 全局追踪器实例
_tracker = RequestTracker()


def get_tracker() -> RequestTracker:
    """获取全局请求追踪器"""
    return _tracker


# ==================== 健康检查 ====================

def get_health_status() -> Dict:
    """系统健康检查"""
    import torch
    import chromadb

    checks = {}

    # GPU 检查
    checks["gpu"] = {
        "available": torch.cuda.is_available(),
        "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "memory_mb": round(torch.cuda.get_device_properties(0).total_memory / 1024 / 1024) if torch.cuda.is_available() else 0,
    }

    # ChromaDB 检查
    try:
        from rag.vector_store import get_document_list
        docs = get_document_list()
        checks["chromadb"] = {"status": "connected", "collections": len(docs)}
    except Exception as e:
        checks["chromadb"] = {"status": "error", "error": str(e)[:100]}

    # LLM 检查
    try:
        from config import DEEPSEEK_API_KEY
        checks["llm"] = {"status": "configured" if DEEPSEEK_API_KEY else "missing_key"}
    except Exception as e:
        logger.warning(f"LLM 健康检查失败: {e}")
        checks["llm"] = {"status": "unknown"}

    # AKShare 检查
    try:
        import akshare
        checks["akshare"] = {"status": "available", "version": akshare.__version__}
    except ImportError:
        checks["akshare"] = {"status": "not_installed"}

    all_healthy = all(
        v.get("status") not in ("error", "missing_key", "not_installed")
        for v in checks.values() if isinstance(v, dict)
    )

    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "checks": checks,
    }


# ==================== 告警阈值 ====================

ALERT_THRESHOLDS = {
    "error_rate": 10.0,        # 错误率 > 10%
    "latency_p95_ms": 10000,   # P95延迟 > 10s
    "success_rate": 80.0,      # 成功率 < 80%
}


def check_alerts() -> List[Dict]:
    """检查是否有触发告警阈值"""
    stats = _tracker.get_stats()
    alerts = []

    error_rate = 100 - stats["success_rate"]
    if error_rate > ALERT_THRESHOLDS["error_rate"]:
        alerts.append({
            "level": "warning",
            "metric": "error_rate",
            "value": f"{error_rate}%",
            "threshold": f">{ALERT_THRESHOLDS['error_rate']}%",
            "message": f"错误率 {error_rate}% 超过阈值 {ALERT_THRESHOLDS['error_rate']}%",
        })

    if stats["latency_p95_ms"] > ALERT_THRESHOLDS["latency_p95_ms"]:
        alerts.append({
            "level": "warning",
            "metric": "latency_p95",
            "value": f"{stats['latency_p95_ms']}ms",
            "threshold": f">{ALERT_THRESHOLDS['latency_p95_ms']}ms",
            "message": f"P95延迟 {stats['latency_p95_ms']}ms 超过阈值",
        })

    if stats["success_rate"] < ALERT_THRESHOLDS["success_rate"]:
        alerts.append({
            "level": "critical",
            "metric": "success_rate",
            "value": f"{stats['success_rate']}%",
            "threshold": f"<{ALERT_THRESHOLDS['success_rate']}%",
            "message": f"成功率 {stats['success_rate']}% 低于阈值 {ALERT_THRESHOLDS['success_rate']}%",
        })

    return alerts


def _format_duration(seconds: float) -> str:
    """格式化时长"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
