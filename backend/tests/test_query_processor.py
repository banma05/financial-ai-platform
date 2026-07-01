"""
query_processor.py 单元测试

覆盖：财务术语展开、短句扩写、余弦校验、完整处理流程
"""
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from rag.query_processor import (
    expand_financial_terms,
    FINANCIAL_TERM_MAP,
    SHORT_QUERY_THRESHOLD,
    MIN_SIMILARITY,
    _cosine_sim,
    expand_query,
    validate_expansion,
    process_query,
)


# ============ expand_financial_terms ============


class TestExpandFinancialTerms:
    """财务术语缩写展开"""

    def test_归母净利润展开(self):
        result = expand_financial_terms("归母净利润是多少")
        assert "归属于母公司股东的净利润" in result
        assert "归母净利润" in result  # 保留原文

    def test_扣非净利润展开(self):
        result = expand_financial_terms("扣非净利润增长了")
        assert "扣除非经常性损益的净利润" in result

    def test_ROE展开(self):
        result = expand_financial_terms("ROE是多少")
        assert "净资产收益率" in result
        assert "ROE" in result  # 保留原文

    def test_EPS展开(self):
        result = expand_financial_terms("EPS增长了")
        assert "基本每股收益" in result

    def test_营收展开(self):
        result = expand_financial_terms("营收怎么算")
        assert "营业收入" in result

    def test_经营现金流展开(self):
        result = expand_financial_terms("经营现金流情况")
        assert "经营活动产生的现金流量净额" in result

    def test_多个术语同时展开(self):
        """query 包含多个术语时全部展开"""
        result = expand_financial_terms("ROE和EPS对比")
        assert "净资产收益率" in result
        assert "基本每股收益" in result

    def test_无术语不修改(self):
        result = expand_financial_terms("今天天气怎么样")
        assert result == "今天天气怎么样"

    def test_空字符串(self):
        result = expand_financial_terms("")
        assert result == ""

    def test_长词优先_短词不覆盖(self):
        """"归母净利"和"归母净利润"都在术语表中，长词应先匹配"""
        result = expand_financial_terms("归母净利润增长了")
        # 应展开为长词的全称，且不重复展开短词
        assert "归属于母公司股东的净利润" in result

    def test_已覆盖位置不重复展开(self):
        """"归母净利润"中的"净利"不应再被独立展开"""
        # "净利"不在术语表中，但验证这个机制
        result = expand_financial_terms("归母净利润多少")
        # 只应展开一次
        count = result.count("归属于母公司股东的净利润")
        assert count == 1

    def test_只有缩写没有全称的术语保持原文(self):
        """资产负债率的缩写=全称，不应修改"""
        original = "资产负债率是多少"
        result = expand_financial_terms(original)
        # 不应该出现"资产负债率(资产负债率)"
        assert "资产负债率(资产负债率)" not in result


# ============ 术语表一致性检查 ============


class TestFinancialTermMap:
    """术语表自身一致性"""

    def test_所有缩写都有对应全称(self):
        for abbr, full in FINANCIAL_TERM_MAP.items():
            assert len(abbr) > 0
            assert len(full) > 0

    def test_缩写不等于全称的才需要展开(self):
        """缩写==全称的条目在 expand_financial_terms 中被跳过"""
        for abbr, full in FINANCIAL_TERM_MAP.items():
            if abbr == full:
                # 这个条目不会参与展开（在代码中被 continue 跳过）
                pass


# ============ _cosine_sim ============


class TestCosineSim:
    """余弦相似度计算"""

    def test_相同向量_相似度为1(self):
        v = np.array([1.0, 2.0, 3.0])
        sim = _cosine_sim(v, v)
        assert sim == pytest.approx(1.0, abs=0.001)

    def test_正交向量_相似度为0(self):
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        sim = _cosine_sim(a, b)
        assert sim == pytest.approx(0.0, abs=0.001)

    def test_反向向量_相似度为负1(self):
        a = np.array([1.0, 2.0])
        b = np.array([-1.0, -2.0])
        sim = _cosine_sim(a, b)
        assert sim == pytest.approx(-1.0, abs=0.001)

    def test_零向量_不抛异常(self):
        """零向量 norm=0，加了 1e-8 防止除零"""
        a = np.array([1.0, 2.0])
        b = np.array([0.0, 0.0])
        sim = _cosine_sim(a, b)
        # 不会抛异常，结果接近 0
        assert not np.isnan(sim)


# ============ expand_query（mock LLM）============


class TestExpandQuery:
    """短句扩写"""

    def test_短query触发扩写(self):
        """长度 < SHORT_QUERY_THRESHOLD 时触发 LLM 扩写"""
        short = "净利润？"
        assert len(short) < SHORT_QUERY_THRESHOLD

        with patch("rag.query_processor.llm_chat", return_value="比亚迪2024年净利润是多少"):
            result = expand_query(short)
        assert len(result) > len(short)
        assert "比亚迪" in result

    def test_长query跳过扩写(self):
        """长度 >= 阈值时不扩写，直接返回原文"""
        long_query = "请问比亚迪2024年年报中归属于母公司股东的净利润相比上一年度的变化情况如何"
        with patch("rag.query_processor.llm_chat") as mock_chat:
            result = expand_query(long_query)
        mock_chat.assert_not_called()
        assert result == long_query

    def test_LLM异常回退原文(self):
        """LLM 调用失败时返回原文"""
        short = "净利润？"
        with patch("rag.query_processor.llm_chat", side_effect=Exception("API错误")):
            result = expand_query(short)
        assert result == short


# ============ validate_expansion（mock embedding）============


class TestValidateExpansion:
    """余弦相似度校验"""

    def test_相同文本_通过校验(self):
        """原文和扩写相同时直接返回原文"""
        result = validate_expansion("测试", "测试")
        assert result == "测试"

    def test_高相似度_接受扩写(self):
        """相似度 >= 阈值，接受扩写结果"""
        with patch("rag.query_processor._embed_query") as mock_embed:
            # 返回相同向量 → 相似度为 1.0
            mock_embed.return_value = np.array([1.0, 0.0])
            result = validate_expansion("原文", "扩写后文本")
        assert result == "扩写后文本"

    def test_低相似度_废弃扩写(self):
        """相似度 < 阈值，废弃扩写，用原文"""
        with patch("rag.query_processor._embed_query") as mock_embed:
            # 正交向量 → 相似度为 0
            mock_embed.side_effect = [
                np.array([1.0, 0.0]),  # 原文向量
                np.array([0.0, 1.0]),  # 扩写向量（正交）
            ]
            result = validate_expansion("原文", "完全不相关的扩写")
        assert result == "原文"


# ============ process_query（集成流程）============


class TestProcessQuery:
    """完整 Query 处理流程"""

    def test_正常短query(self):
        with patch("rag.query_processor._embed_query", return_value=np.array([1.0, 0.0])):
            with patch("rag.query_processor.llm_chat", return_value="比亚迪2024年营收"):
                result = process_query("营收多少")
        assert len(result) > 0

    def test_空query(self):
        result = process_query("")
        assert result == ""

    def test_纯空格query(self):
        result = process_query("   ")
        assert result == "   "  # 原样返回（空白query不处理）

    def test_长query不走扩写(self):
        """长 query 直接通过，不调 LLM"""
        long_q = "比亚迪2024年年报中归属于母公司股东的净利润是多少亿元"
        with patch("rag.query_processor.llm_chat") as mock_chat:
            with patch("rag.query_processor._embed_query", return_value=np.array([1.0, 0.0])):
                result = process_query(long_q)
        mock_chat.assert_not_called()

    def test_含术语的长query_仅展开术语(self):
        """即使不扩写，术语展开仍生效"""
        long_q = "请问ROE和EPS相比去年的变化趋势是什么样的请详细分析"
        with patch("rag.query_processor.llm_chat"):
            with patch("rag.query_processor._embed_query", return_value=np.array([1.0, 0.0])):
                result = process_query(long_q)
        assert "净资产收益率" in result
        assert "基本每股收益" in result
        assert "ROE" in result
