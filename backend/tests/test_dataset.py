"""
测试集验证 — 确保 test_questions.json 格式正确、覆盖完整
"""
import json
from pathlib import Path

import pytest

TEST_SET_PATH = Path(__file__).parent.parent.parent / "data" / "test_questions.json"


@pytest.fixture
def dataset():
    with open(TEST_SET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============ 结构校验 ============


class TestDatasetStructure:
    """测试集 JSON 结构"""

    def test_文件存在(self):
        assert TEST_SET_PATH.exists(), f"测试集文件不存在: {TEST_SET_PATH}"

    def test_meta字段完整(self, dataset):
        meta = dataset["meta"]
        assert "name" in meta
        assert "total_questions" in meta
        assert meta["total_questions"] == len(dataset["questions"]), \
            f"meta.total_questions={meta['total_questions']} ≠ 实际{len(dataset['questions'])}"

    def test_每道题字段完整(self, dataset):
        required = ["id", "category", "difficulty", "query", "expected_keywords", "ideal_pages", "min_recall"]
        for q in dataset["questions"]:
            for field in required:
                assert field in q, f"{q.get('id', '?')}: 缺少字段 '{field}'"

    def test_ID连续不重复(self, dataset):
        ids = [q["id"] for q in dataset["questions"]]
        assert len(ids) == len(set(ids)), f"存在重复ID: {ids}"
        # 验证格式为 Q01-Q50
        for i, qid in enumerate(sorted(ids), start=1):
            assert qid == f"Q{i:02d}", f"ID不连续: 期望 Q{i:02d}, 实际 {qid}"


# ============ 内容校验 ============


class TestDatasetContent:
    """测试集内容质量"""

    def test_所有题都有期望关键词(self, dataset):
        """除非 min_recall=0（文档无答案类），否则必须有 expected_keywords"""
        for q in dataset["questions"]:
            if q["min_recall"] > 0:
                assert len(q["expected_keywords"]) > 0, \
                    f"{q['id']}: min_recall>0 但 expected_keywords 为空"

    def test_easy题min_recall不大于2(self, dataset):
        """easy 题目不应要求太多关键词"""
        for q in dataset["questions"]:
            if q["difficulty"] == "easy":
                assert q["min_recall"] <= 2, \
                    f"{q['id']}: easy 题目 min_recall={q['min_recall']} 过高"

    def test_hard题至少需要2个关键词(self, dataset):
        for q in dataset["questions"]:
            if q["difficulty"] == "hard":
                assert q["min_recall"] >= 2, \
                    f"{q['id']}: hard 题目 min_recall={q['min_recall']} 过低"

    def test_每道题query非空(self, dataset):
        for q in dataset["questions"]:
            assert len(q["query"].strip()) > 0, f"{q['id']}: query 为空"


# ============ 覆盖度校验 ============


class TestDatasetCoverage:
    """测试集覆盖度"""

    VALID_CATEGORIES = [
        "数值查询", "趋势分析", "对比分析", "定义解释",
        "风险分析", "综合分析", "综合推理", "跨文档检索",
        "边界异常", "脏数据",
    ]
    VALID_DIFFICULTIES = ["easy", "medium", "hard"]
    EXPECTED_CATEGORIES = set(VALID_CATEGORIES)

    def test_类别完整(self, dataset):
        """所有10个类别都有覆盖"""
        actual = {q["category"] for q in dataset["questions"]}
        missing = self.EXPECTED_CATEGORIES - actual
        assert not missing, f"缺失类别: {missing}"

    def test_难度完整(self, dataset):
        """三个难度都有覆盖"""
        actual = {q["difficulty"] for q in dataset["questions"]}
        assert actual == {"easy", "medium", "hard"}, f"缺失难度: {actual}"

    def test_类别值合法(self, dataset):
        for q in dataset["questions"]:
            assert q["category"] in self.VALID_CATEGORIES, \
                f"{q['id']}: 未知类别 '{q['category']}'"

    def test_难度值合法(self, dataset):
        for q in dataset["questions"]:
            assert q["difficulty"] in self.VALID_DIFFICULTIES, \
                f"{q['id']}: 未知难度 '{q['difficulty']}'"

    def test_每个难度最少5题(self, dataset):
        diffs = {"easy": 0, "medium": 0, "hard": 0}
        for q in dataset["questions"]:
            diffs[q["difficulty"]] += 1
        for d, count in diffs.items():
            assert count >= 5, f"难度 '{d}' 仅 {count} 题，期望 ≥5"

    def test_正常样本占比合理(self, dataset):
        """正常样本（非边界异常/脏数据）应占多数"""
        total = len(dataset["questions"])
        edge = sum(1 for q in dataset["questions"] if q["category"] in ("边界异常", "脏数据"))
        normal = total - edge
        ratio = normal / total
        assert ratio >= 0.7, f"正常样本仅占 {ratio:.0%}，期望 ≥70%"


# ============ 跨文档覆盖 ============


class TestCrossDocumentCoverage:
    """跨文档检索覆盖"""

    def test_跨文档题不少于3题(self, dataset):
        cross = [q for q in dataset["questions"] if q["category"] == "跨文档检索"]
        assert len(cross) >= 3, f"跨文档检索仅 {len(cross)} 题，期望 ≥3"

    def test_比亚迪专项不少于3题(self, dataset):
        byd = [q for q in dataset["questions"] if "比亚迪" in q["query"]]
        assert len(byd) >= 3, f"比亚迪专项仅 {len(byd)} 题，期望 ≥3"

    def test_腾讯专项不少于3题(self, dataset):
        tx = [q for q in dataset["questions"] if "腾讯" in q["query"]]
        assert len(tx) >= 3, f"腾讯专项仅 {len(tx)} 题，期望 ≥3"
