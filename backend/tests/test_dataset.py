"""
V8.0 评测集验证 — 确保三层评测数据格式正确

验证 sql_questions.json / agent_questions.json / rag_questions.json 的结构和覆盖
"""
import json
from pathlib import Path
import pytest

DATA_DIR = Path(__file__).parent.parent.parent / "evaluation" / "data"

SQL_PATH = DATA_DIR / "sql_questions.json"
AGENT_PATH = DATA_DIR / "agent_questions.json"
RAG_PATH = DATA_DIR / "rag_questions.json"


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============ SQL 评测集 ============

class TestSQLDataset:
    @pytest.fixture
    def data(self):
        return _load(SQL_PATH)

    def test_文件存在(self):
        assert SQL_PATH.exists()

    def test_20题(self, data):
        assert len(data["questions"]) == 20

    def test_字段完整(self, data):
        required = ["id", "category", "difficulty", "query", "expected_values", "tolerance_pct", "tests"]
        for q in data["questions"]:
            for f in required:
                assert f in q, f"{q.get('id','?')}: 缺字段 '{f}'"

    def test_ID以S开头连续(self, data):
        ids = [q["id"] for q in data["questions"]]
        expected = [f"S{i:02d}" for i in range(1, 21)]
        for e in expected:
            assert e in ids, f"缺ID: {e}"

    def test_三难度都有(self, data):
        diffs = {q["difficulty"] for q in data["questions"]}
        assert diffs >= {"easy", "medium", "hard"}

    def test_边界题正确返回空(self, data):
        """S17-S19: expected_values为空→正确答案是没找到数据"""
        for q in data["questions"]:
            if q["id"] in ("S17", "S18", "S19"):
                assert q["expected_values"] == {}, f"{q['id']}: 边界题应expect空"


# ============ Agent 评测集 ============

class TestAgentDataset:
    @pytest.fixture
    def data(self):
        return _load(AGENT_PATH)

    def test_文件存在(self):
        assert AGENT_PATH.exists()

    def test_15题(self, data):
        assert len(data["questions"]) == 15

    def test_字段完整(self, data):
        required = ["id", "category", "difficulty", "query", "required_numbers", "required_chart", "target_latency_s"]
        for q in data["questions"]:
            for f in required:
                assert f in q, f"{q.get('id','?')}: 缺字段 '{f}'"

    def test_五个类别各3题(self, data):
        cats = {}
        for q in data["questions"]:
            cats[q["category"]] = cats.get(q["category"], 0) + 1
        for c in ["盈利能力", "成长性", "现金流", "风险扫描", "杜邦分析"]:
            assert cats.get(c, 0) == 3, f"类别'{c}'期望3题, 实际{cats.get(c, 0)}"

    def test_全A股(self, data):
        """V8.0 不再包含港股（腾讯）"""
        for q in data["questions"]:
            assert "腾讯" not in q["query"], f"{q['id']}: 含港股腾讯"

    def test_耗时目标合理(self, data):
        for q in data["questions"]:
            t = q["target_latency_s"]
            if q["difficulty"] == "easy":
                assert t <= 3, f"{q['id']}: easy 耗时目标 {t}s > 3s"
            elif q["difficulty"] == "hard":
                assert t <= 8, f"{q['id']}: hard 耗时目标 {t}s > 8s"


# ============ RAG 评测集 ============

class TestRAGDataset:
    @pytest.fixture
    def data(self):
        return _load(RAG_PATH)

    def test_文件存在(self):
        assert RAG_PATH.exists()

    def test_15题(self, data):
        assert len(data["questions"]) == 15

    def test_字段完整(self, data):
        required = ["id", "category", "difficulty", "query", "expected_answer_type", "must_contain_sources", "min_sources", "tests"]
        for q in data["questions"]:
            for f in required:
                assert f in q, f"{q.get('id','?')}: 缺字段 '{f}'"

    def test_ID以R开头连续(self, data):
        ids = [q["id"] for q in data["questions"]]
        expected = [f"R{i:02d}" for i in range(1, 16)]
        for e in expected:
            assert e in ids, f"缺ID: {e}"

    def test_三难度都有(self, data):
        diffs = {q["difficulty"] for q in data["questions"]}
        assert diffs >= {"easy", "medium", "hard"}

    def test_含边界测试(self, data):
        """至少有超短Query和无答案测试"""
        cats = {q["category"] for q in data["questions"]}
        assert "边界测试" in cats

    def test_must_contain_sources合理(self, data):
        """must_contain_sources=False 的题 min_sources 应为 0"""
        for q in data["questions"]:
            if not q["must_contain_sources"]:
                assert q["min_sources"] == 0, \
                    f"{q['id']}: must_contain_sources=False 但 min_sources={q['min_sources']}"