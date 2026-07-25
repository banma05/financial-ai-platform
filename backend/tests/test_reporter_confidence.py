"""
V9.1: Reporter 置信度章节测试 — 验证 V9.0 的重大 Bug 已被修复。

V9.0 Bug: _build_confidence_section 用 isinstance(r, dict) 守卫，
但实际传入的是 TaskResult BaseModel，导致章节永远为空。
V9.1 修复: hasattr(r, 'model_dump') 兼容 BaseModel。
"""

import pytest
from agent.reporter import Reporter
from agent.schemas import TaskResult
from agent.schemas import AnalysisTask


@pytest.fixture
def reporter():
    return Reporter()


# ── 核心修复验证 ──

def test_confidence_with_basemodel(reporter):
    """TaskResult(BaseModel) 输入 → 置信度章节有实质内容（V9.0 Bug 修复）"""
    results = [
        TaskResult(
            task_id="t1", task_type="data_query", success=True,
            result={"营收_2024": 1708.99},
            source="sql", confidence=0.99, display_name="营收_2024",
        ),
        TaskResult(
            task_id="t2", task_type="calculate", success=True,
            result=91.18,
            source="computed", confidence=0.85, display_name="毛利率",
        ),
    ]

    section = reporter._build_confidence_section(results, {})
    assert len(section) > 100, f"置信度章节太短: {section}"
    assert "高" in section or "中" in section or "低" in section, "缺少置信度等级"
    assert "SQL 直查" in section, "缺少来源说明"


def test_confidence_with_dict_input(reporter):
    """仍然兼容 dict 输入（向后兼容）"""
    results = [
        {"task_id": "t1", "source": "sql", "confidence": 0.95},
    ]
    section = reporter._build_confidence_section(results, {})
    assert "SQL 直查" in section


def test_confidence_with_mixed_input(reporter):
    """混合 BaseModel + dict 输入"""
    results = [
        TaskResult(task_id="t1", source="sql", confidence=0.99, task_type="data_query", success=True),
        {"task_id": "t2", "source": "computed", "confidence": 0.80},
    ]
    section = reporter._build_confidence_section(results, {})
    assert "SQL 直查" in section
    assert "公式推算" in section


def test_confidence_empty_results(reporter):
    """空结果列表 → 章节只有表头"""
    section = reporter._build_confidence_section([], {})
    assert "## 七、数据可靠度说明" in section
    # 没有置信度数据时不应有等级
    assert "整体数据可靠度" not in section


def test_confidence_all_sql(reporter):
    """全部 SQL 来源 → 只显示 SQL 直查，不显示 fallback/computed"""
    results = [
        TaskResult(task_id="t1", source="sql", confidence=0.99, task_type="data_query", success=True),
        TaskResult(task_id="t2", source="sql", confidence=0.98, task_type="data_query", success=True),
    ]
    section = reporter._build_confidence_section(results, {})
    assert "SQL 直查" in section
    assert "字段回退" not in section
    assert "公式推算" not in section


def test_confidence_low_confidence_label(reporter):
    """低置信度 → 显示「低」"""
    results = [
        TaskResult(task_id="t1", source="rag", confidence=0.50, task_type="rag_context", success=True),
        TaskResult(task_id="t2", source="computed", confidence=0.60, task_type="calculate", success=True),
    ]
    section = reporter._build_confidence_section(results, {})
    assert "低" in section
    assert "年报解读" in section
