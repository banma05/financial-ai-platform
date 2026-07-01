"""
evaluator.py 单元测试

覆盖：文本归一化、关键词匹配、R@k、MRR、NDCG、检索评测、LLM评测（mock）
"""
import json
import math
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from rag.evaluator import (
    _normalize_text,
    _keyword_in_text,
    recall_at_k,
    precision_at_k,
    mrr,
    ndcg_at_k,
    evaluate_retrieval,
    evaluate_context_recall,
    evaluate_faithfulness,
    full_evaluation,
    batch_evaluate,
    save_report,
    get_latest_report,
)

# ============ 测试辅助 ============


def make_chunk(content: str, source: str = "test.pdf", page: int = 1) -> dict:
    """快速构造测试用 chunk"""
    return {"content": content, "source": source, "page": page}


# ============ _normalize_text ============


class TestNormalizeText:
    """财务文本归一化"""

    def test_去空格(self):
        assert _normalize_text("营 业 收 入") == "营业收入"

    def test_去多余空白(self):
        assert _normalize_text("净利润   增长   10%") == "净利润增长10%"

    def test_千分位逗号去除_整数(self):
        """1,741 → 1741"""
        assert _normalize_text("营收1,741亿元") == "营收1741亿元"

    def test_千分位逗号去除_带小数(self):
        """1,741.44 → 1741.44"""
        assert _normalize_text("1,741.44亿") == "1741.44亿"

    def test_多个千分位(self):
        """1,234,567 → 1234567"""
        assert _normalize_text("营收1,234,567万元") == "营收1234567万元"

    def test_全角数字转半角(self):
        """全角１２３ → 半角 123"""
        assert _normalize_text("营收１２３亿元") == "营收123亿元"

    def test_全角百分号(self):
        assert _normalize_text("毛利率５０％") == "毛利率50%"

    def test_正常数字不变(self):
        assert _normalize_text("营收100亿") == "营收100亿"

    def test_空字符串(self):
        assert _normalize_text("") == ""


# ============ _keyword_in_text ============


class TestKeywordInText:
    """关键词在文本中的匹配"""

    def test_精确匹配(self):
        assert _keyword_in_text("营业收入", "公司营业收入大幅增长") is True

    def test_空格不敏感(self):
        """关键词和文本中空格差异不应影响匹配"""
        assert _keyword_in_text("营业收入", "营 业 收 入 大幅增长") is True

    def test_未命中(self):
        assert _keyword_in_text("净利润", "营业收入大幅增长") is False

    def test_数字千分位不敏感(self):
        """关键词是"1741"，文本中是"1,741"，应匹配"""
        assert _keyword_in_text("1741亿元", "营收1,741亿元") is True

    def test_英文关键词(self):
        assert _keyword_in_text("ROE", "公司ROE达到15%") is True


# ============ recall_at_k ============


class TestRecallAtK:
    """召回率@k"""

    def test_全部命中_k5(self):
        chunks = [make_chunk(f"关键词{i}的数据") for i in range(10)]
        result = recall_at_k(
            "测试", ["关键词1", "关键词2", "关键词3"], chunks, k=5
        )
        assert result["recall@k"] == 1.0
        assert len(result["matched"]) == 3
        assert len(result["missed"]) == 0

    def test_部分命中(self):
        chunks = [make_chunk("关键词1的数据"), make_chunk("无关内容"),
                   make_chunk("更多无关"), make_chunk("还是无关"), make_chunk("无关")]
        result = recall_at_k(
            "测试", ["关键词1", "关键词2", "关键词3"], chunks, k=5
        )
        assert result["recall@k"] == pytest.approx(1 / 3, abs=0.01)
        assert "关键词1" in result["matched"]
        assert "关键词2" in result["missed"]

    def test_零命中(self):
        chunks = [make_chunk("完全无关的内容") for _ in range(5)]
        result = recall_at_k(
            "测试", ["关键词A", "关键词B"], chunks, k=5
        )
        assert result["recall@k"] == 0.0
        assert len(result["missed"]) == 2

    def test_空关键词列表(self):
        result = recall_at_k("测试", [], [make_chunk("x")], k=5)
        assert result["recall@k"] == 0.0

    def test_空chunk列表(self):
        result = recall_at_k("测试", ["测试"], [], k=5)
        assert result["recall@k"] == 0.0

    def test_k取1_仅看第一个chunk(self):
        """k=1 时仅看 top-1"""
        chunks = [make_chunk("无关"), make_chunk("关键词1在这里")]
        result = recall_at_k("测试", ["关键词1"], chunks, k=1)
        assert result["recall@k"] == 0.0  # 第一个chunk没有命中的

    def test_k取3_命中在第三位(self):
        chunks = [make_chunk("无1"), make_chunk("无2"), make_chunk("关键词1命中")]
        result = recall_at_k("测试", ["关键词1"], chunks, k=3)
        assert result["recall@k"] == 1.0  # k=3 覆盖到第3个


# ============ precision_at_k ============


class TestPrecisionAtK:
    """精确率@k"""

    def test_全部命中(self):
        chunks = [make_chunk(f"关键词{i}") for i in range(5)]
        result = precision_at_k(["关键词"], chunks, k=5)
        # 所有5个chunk都包含"关键词" → 命中5/5
        assert result["precision@k"] == 1.0

    def test_一半命中(self):
        chunks = [
            make_chunk("关键词在这里"),
            make_chunk("无关内容"),
            make_chunk("关键词也在"),
            make_chunk("还是无关"),
            make_chunk("无关"),
        ]
        result = precision_at_k(["关键词"], chunks, k=5)
        assert result["precision@k"] == 0.4  # 2/5

    def test_零命中(self):
        chunks = [make_chunk("无关") for _ in range(5)]
        result = precision_at_k(["关键词"], chunks, k=5)
        assert result["precision@k"] == 0.0

    def test_k值约束(self):
        """chunk 少于 k 时用实际数量"""
        chunks = [make_chunk("关键词在这里")]
        result = precision_at_k(["关键词"], chunks, k=10)
        assert result["precision@k"] == 0.1  # 1/10, k 固定为参数值


# ============ MRR ============


class TestMRR:
    """平均倒数排名"""

    def test_第一个命中(self):
        chunks = [make_chunk("关键词命中"), make_chunk("无关")]
        result = mrr(["关键词"], chunks)
        assert result["mrr"] == 1.0  # 1/1
        assert result["first_rank"] == 1

    def test_第三个命中(self):
        chunks = [make_chunk("无1"), make_chunk("无2"), make_chunk("关键词")]
        result = mrr(["关键词"], chunks)
        assert result["mrr"] == pytest.approx(1.0 / 3, abs=0.001)
        assert result["first_rank"] == 3

    def test_未命中(self):
        result = mrr(["关键词"], [make_chunk("无关")])
        assert result["mrr"] == 0.0
        assert result["first_rank"] is None

    def test_空输入(self):
        result = mrr([], [])
        assert result["mrr"] == 0.0


# ============ NDCG@k ============


class TestNDCGAtK:
    """归一化折损累计增益"""

    def test_全部命中靠前_高分(self):
        """所有关键词都在前几个chunk中，NDCG 应接近 1"""
        chunks = [make_chunk(f"关键词{i}命中") for i in range(5)]
        result = ndcg_at_k(["关键词1", "关键词2", "关键词3"], chunks, k=5)
        assert result["ndcg@k"] > 0.5

    def test_命中靠后_低分(self):
        """关键词只出现在后面的chunk中"""
        chunks = [
            make_chunk("无"), make_chunk("无"), make_chunk("无"),
            make_chunk("无"), make_chunk("关键词1+关键词2+关键词3"),
        ]
        result = ndcg_at_k(["关键词1", "关键词2", "关键词3"], chunks, k=5)
        # 靠后的位置贡献小
        dcgs_late = result["dcg"]
        # 对比：如果关键词在前面
        chunks_front = [
            make_chunk("关键词1+关键词2+关键词3"), make_chunk("无"),
            make_chunk("无"), make_chunk("无"), make_chunk("无"),
        ]
        result_front = ndcg_at_k(["关键词1", "关键词2", "关键词3"], chunks_front, k=5)
        assert dcgs_late < result_front["dcg"], "靠后的 dcg 应小于靠前"

    def test_零命中(self):
        result = ndcg_at_k(["关键词1"], [make_chunk("无关")], k=5)
        assert result["ndcg@k"] == 0.0

    def test_空输入(self):
        result = ndcg_at_k([], [], k=5)
        assert result["ndcg@k"] == 0.0


# ============ evaluate_retrieval ============


class TestEvaluateRetrieval:
    """一站式检索评测"""

    def test_返回所有指标(self):
        chunks = [make_chunk(f"关键词命中{i}") for i in range(10)]
        metrics = evaluate_retrieval(
            "测试Query", ["关键词命中1", "关键词命中2", "关键词命中3"], chunks, k_values=[1, 3, 5]
        )
        assert "recall@1" in metrics
        assert "recall@3" in metrics
        assert "recall@5" in metrics
        assert "precision@1" in metrics
        assert "precision@3" in metrics
        assert "precision@5" in metrics
        assert "ndcg@1" in metrics
        assert "ndcg@3" in metrics
        assert "ndcg@5" in metrics
        assert "mrr" in metrics
        assert "first_rank" in metrics

    def test_完美检索(self):
        """前几个 chunk 全部命中所有关键词"""
        chunks = [make_chunk("A B C") for _ in range(5)]
        metrics = evaluate_retrieval("test", ["A"], chunks, k_values=[5])
        assert metrics["recall@5"] == 1.0
        assert metrics["mrr"] == 1.0


# ============ LLM 评测（mock）============


class TestLLMEvaluation:
    """LLM-as-Judge 评测（mock LLM 调用）"""

    def test_context_recall_高分(self):
        """mock LLM 返回高分"""
        with patch("rag.evaluator.llm_judge", return_value="95|答案完全基于文档"):
            result = evaluate_context_recall(
                "营收多少", "营收达到100亿", [make_chunk("营收达到100亿")]
            )
        assert result["recall"] == 0.95
        assert "完全基于" in result["reason"]

    def test_context_recall_低分(self):
        with patch("rag.evaluator.llm_judge", return_value="20|基本找不到支撑"):
            result = evaluate_context_recall(
                "营收多少", "营收达到100亿", [make_chunk("公司成立于2000年")]
            )
        assert result["recall"] == 0.20

    def test_context_recall_无检索结果(self):
        """无检索结果时直接返回 0"""
        result = evaluate_context_recall("营收多少", "营收达到100亿", [])
        assert result["recall"] == 0.0

    def test_context_recall_解析失败容错(self):
        """LLM 返回格式异常时兜底返回 0.5"""
        with patch("rag.evaluator.llm_judge", return_value="not-a-number"):
            result = evaluate_context_recall(
                "营收多少", "营收100亿", [make_chunk("营收100亿")]
            )
        assert result["recall"] == 0.5

    def test_faithfulness_满分(self):
        with patch("rag.evaluator.llm_judge", return_value="100|完全基于文档"):
            result = evaluate_faithfulness(
                "营收100亿", [make_chunk("营收达到100亿")]
            )
        assert result["faithfulness"] == 1.0

    def test_faithfulness_空答案(self):
        result = evaluate_faithfulness("", [make_chunk("x")])
        assert result["faithfulness"] == 1.0


class TestFullEvaluation:
    """完整评测（context_recall + faithfulness）"""

    def test_双高_质量良好(self):
        with patch("rag.evaluator.llm_judge") as mock_judge:
            mock_judge.side_effect = ["95|好", "90|好"]
            result = full_evaluation(
                "营收多少", "100亿", [make_chunk("营收100亿")]
            )
        assert result["context_recall"]["recall"] == 0.95
        assert result["faithfulness"]["faithfulness"] == 0.90
        assert "良好" in result["suggestion"]

    def test_召回低_建议优化检索(self):
        with patch("rag.evaluator.llm_judge") as mock_judge:
            mock_judge.side_effect = ["60|一般", "90|好"]
            result = full_evaluation(
                "营收多少", "100亿", [make_chunk("无关")]
            )
        assert "检索" in result["suggestion"] or "召回" in result["suggestion"]

    def test_忠实度低_建议优化Prompt(self):
        with patch("rag.evaluator.llm_judge") as mock_judge:
            mock_judge.side_effect = ["90|好", "60|一般"]
            result = full_evaluation(
                "营收多少", "编造的内容", [make_chunk("审计报告")]
            )
        assert "Prompt" in result["suggestion"] or "忠实" in result["suggestion"]


# ============ 报告持久化 ============


class TestSaveAndGetReport:
    """评测报告保存与读取"""

    def test_save_and_retrieve(self):
        report = {"summary": {"avg_recall@5": 0.85}}
        path = save_report(report)
        saved_path = Path(path)
        assert saved_path.exists()

        # 验证缓存
        cached = get_latest_report()
        assert cached is not None
        assert cached["summary"]["avg_recall@5"] == 0.85

        # 清理
        saved_path.unlink()

    def test_custom_output_path(self, tmp_path):
        report = {"test": True}
        output = str(tmp_path / "custom_report.json")
        save_report(report, output_path=output)
        assert Path(output).exists()


# ============ 批量评测 ============


class TestBatchEvaluate:
    """批量评测"""

    def test_基本流程(self, tmp_path):
        """用临时测试集跑批量评测"""
        test_set = {
            "questions": [
                {
                    "id": "Q1",
                    "query": "比亚迪营收多少",
                    "category": "财务指标",
                    "difficulty": "easy",
                    "expected_keywords": ["营业收入"],
                },
                {
                    "id": "Q2",
                    "query": "茅台毛利率",
                    "category": "盈利能力",
                    "difficulty": "medium",
                    "expected_keywords": ["毛利率"],
                },
            ]
        }
        test_file = tmp_path / "test_batch.json"
        test_file.write_text(json.dumps(test_set, ensure_ascii=False), encoding="utf-8")

        def mock_search(query: str, top_k: int = 5):
            # 简单 mock：永远返回包含关键词的 chunk
            return [make_chunk("营业收入 毛利率 100亿")]

        report = batch_evaluate(
            str(test_file), mock_search, top_k=5, verbose=False
        )

        assert report["meta"]["num_questions"] == 2
        assert report["summary"]["avg_recall@5"] == 1.0  # mock 总是命中
        assert "easy" in report["by_difficulty"]
        assert "medium" in report["by_difficulty"]
        assert "财务指标" in report["by_category"]
        assert "盈利能力" in report["by_category"]
        assert len(report["details"]) == 2

    def test_文件不存在_抛异常(self):
        with pytest.raises(FileNotFoundError):
            batch_evaluate("/nonexistent/test.json", lambda q, k: [])

    def test_空测试集_抛异常(self, tmp_path):
        test_file = tmp_path / "empty.json"
        test_file.write_text('{"questions": []}', encoding="utf-8")
        with pytest.raises(ValueError, match="没有题目"):
            batch_evaluate(str(test_file), lambda q, k: [])
