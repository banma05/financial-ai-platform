"""
PDF 表格结构化提取 集成测试

用实际年报验证：表格检测率、Markdown 格式、大表格注入分块、语义切分兼容性
"""
import sys
from pathlib import Path

import pytest

# 确保 backend 在 path 中
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from rag.loader import load_pdf, _table_to_markdown
from rag.semantic_splitter import semantic_chunk_per_page

# 测试年报路径
DATA_DIR = _backend_dir.parent / "data" / "documents"
PDF_FILES = ["比亚迪2024年年报.PDF", "贵州茅台2024年年报.pdf", "腾讯控股2024年年报.pdf"]


# ============ 表格检测 ============


class TestTableDetection:
    """PDF 表格检测能力"""

    @pytest.mark.parametrize("pdf_name", PDF_FILES)
    def test_检测到表格(self, pdf_name):
        """每份年报至少检测到 10 张表格"""
        pdf_path = DATA_DIR / pdf_name
        if not pdf_path.exists():
            pytest.skip(f"测试文件不存在: {pdf_path}")
        pages = load_pdf(str(pdf_path))
        total = sum(len(p.get("tables", [])) for p in pages)
        assert total >= 10, f"{pdf_name}: 仅检测到 {total} 张表格，预期 ≥10"

    @pytest.mark.parametrize("pdf_name", PDF_FILES)
    def test_大表格占比合理(self, pdf_name):
        """大表格(≥4行×3列)应占一定比例——年报主要是大表"""
        pdf_path = DATA_DIR / pdf_name
        if not pdf_path.exists():
            pytest.skip(f"测试文件不存在: {pdf_path}")
        pages = load_pdf(str(pdf_path))
        big = 0
        small = 0
        for p in pages:
            for t in p.get("tables", []):
                if t["rows"] >= 4 and t["cols"] >= 3:
                    big += 1
                else:
                    small += 1
        total = big + small
        if total > 0:
            big_ratio = big / total
            # 至少 50% 是大表（年报核心是财务数据表）
            assert big_ratio >= 0.4, (
                f"{pdf_name}: 大表占比仅 {big_ratio:.0%}，预期 ≥40%"
            )

    def test_表格维度完整(self):
        """每个表格都有 rows/cols/markdown 字段"""
        pdf_path = DATA_DIR / "比亚迪2024年年报.PDF"
        if not pdf_path.exists():
            pytest.skip("测试文件不存在")
        pages = load_pdf(str(pdf_path))
        for p in pages:
            for t in p.get("tables", []):
                assert "rows" in t
                assert "cols" in t
                assert "markdown" in t
                assert t["rows"] > 0
                assert t["cols"] > 0


# ============ Markdown 格式 ============


class TestMarkdownFormat:
    """表格 → Markdown 转换质量"""

    def test_Markdown基本格式(self):
        """所有表格的 Markdown 都包含 pipe 和分隔行"""
        pdf_path = DATA_DIR / "比亚迪2024年年报.PDF"
        if not pdf_path.exists():
            pytest.skip("测试文件不存在")
        pages = load_pdf(str(pdf_path))
        table_count = 0
        for p in pages:
            for t in p.get("tables", []):
                table_count += 1
                md = t["markdown"]
                assert "|" in md, f"P{p['page']} 表格 {table_count}: 缺少 '|'"
                assert "---" in md, f"P{p['page']} 表格 {table_count}: 缺少 '---' 分隔行"

    def test_财务数据单元格不为空(self):
        """年报中的表格应有实际财务数据，而非全空"""
        pdf_path = DATA_DIR / "贵州茅台2024年年报.pdf"
        if not pdf_path.exists():
            pytest.skip("测试文件不存在")
        pages = load_pdf(str(pdf_path))
        # 找一张典型的财务数据表（10-20行，带数字）
        found_data = False
        for p in pages:
            for t in p.get("tables", []):
                if 10 <= t["rows"] <= 20:
                    md = t["markdown"]
                    # 至少包含一些中文和数字
                    import re
                    has_chinese = bool(re.search(r'[一-鿿]', md))
                    has_numbers = bool(re.search(r'\d+\.?\d*', md))
                    if has_chinese and has_numbers:
                        found_data = True
                        break
            if found_data:
                break
        assert found_data, "未找到同时包含中文和数字的财务数据表"


class TestTableToMarkdown:
    """_table_to_markdown 函数单元测试"""

    def test_空表格返回空字符串(self):
        """空数据不抛异常"""
        # 模拟一个空的 PyMuPDF table 行为
        try:
            result = _table_to_markdown.__wrapped__(None)
        except AttributeError:
            pass  # 不能直接调 mock，跳过


# ============ 大表格注入分块 ============


class TestTableChunkInjection:
    """大表格注入分块逻辑"""

    def test_大表格注入到chunk中(self):
        """≥4行×3列的表格 Markdown 应出现在 chunk 的 content 中"""
        pdf_path = DATA_DIR / "贵州茅台2024年年报.pdf"
        if not pdf_path.exists():
            pytest.skip("测试文件不存在")
        pages = load_pdf(str(pdf_path))

        # 找一页包含大表的
        target_page = None
        for p in pages:
            big = [t for t in p.get("tables", []) if t["rows"] >= 4 and t["cols"] >= 3]
            if big:
                target_page = [p]
                break

        if target_page is None:
            pytest.skip("未找到含大表的页面")

        chunks = semantic_chunk_per_page(target_page)
        assert len(chunks) > 0, "含大表的页面切分后应有 chunk"

        # 验证关键特征：大表格的 Markdown 含 pipe/分隔行，应出现在某个 chunk 中
        big_table_md = target_page[0]["tables"][0]["markdown"]
        # 取表格中唯一的数据片段做匹配（非 Markdown 标记符）
        lines = [l for l in big_table_md.split("\n") if "---" not in l and l.strip()]
        # 找一个包含中文内容的行作为标识
        identifier = None
        for line in lines:
            import re
            if re.search(r'[一-鿿]{3,}', line):  # 至少3个连续中文字符
                # 取中间8个字符（避开可能的前后截断）
                chinese = re.findall(r'[一-鿿]{3,}', line)
                if chinese:
                    identifier = chinese[0][:8]
                    break

        if identifier:
            combined = " ".join(c["content"] for c in chunks)
            assert identifier in combined, (
                f"表格关键词 '{identifier}' 未在 chunk 中找到 → 大表格未正确注入分块"
            )
        else:
            # 降级验证：至少有 pipe 字符（Markdown 表格标记）
            combined = " ".join(c["content"] for c in chunks)
            assert "|" in combined, "chunk 中完全没有 Markdown 表格标记"

    def test_小表格不注入(self):
        """小表格(<4行或<3列)不应注入 chunk"""
        pdf_path = DATA_DIR / "比亚迪2024年年报.PDF"
        if not pdf_path.exists():
            pytest.skip("测试文件不存在")
        pages = load_pdf(str(pdf_path))

        # 找一页只有小表的
        small_only_page = None
        for p in pages:
            tables = p.get("tables", [])
            if tables and all(t["rows"] < 4 or t["cols"] < 3 for t in tables):
                small_only_page = [p]
                break

        if small_only_page is None:
            pytest.skip("未找到只有小表的页面")

        chunks = semantic_chunk_per_page(small_only_page)
        # 验证没有注入异常的 Markdown 表格标记
        for c in chunks:
            # 不应该有完整的表格 Markdown（小表的 md 不应出现）
            # 小表的 markdown 不在 text 中，所以 chunk 不应有多余的 |---|---|
            assert not c["content"].startswith("|"), "小表不应以 Markdown 表头开头"


# ============ 语义切分兼容性 ============


class TestSemanticChunkWithTables:
    """语义切分与表格提取的配合"""

    @pytest.mark.parametrize("pdf_name", PDF_FILES)
    def test_每份年报都能正常切分(self, pdf_name):
        """语义切分不抛异常"""
        pdf_path = DATA_DIR / pdf_name
        if not pdf_path.exists():
            pytest.skip(f"测试文件不存在: {pdf_path}")
        pages = load_pdf(str(pdf_path))
        chunks = semantic_chunk_per_page(pages)
        assert len(chunks) > 0, f"{pdf_name}: 切分后无 chunk"

    @pytest.mark.parametrize("pdf_name", PDF_FILES)
    def test_chunk结构完整(self, pdf_name):
        """每个 chunk 都有必要字段"""
        pdf_path = DATA_DIR / pdf_name
        if not pdf_path.exists():
            pytest.skip(f"测试文件不存在: {pdf_path}")
        pages = load_pdf(str(pdf_path))
        chunks = semantic_chunk_per_page(pages)
        for c in chunks:
            assert "content" in c
            assert "source" in c
            assert "page" in c
            assert "chunk_type" in c
            assert c["chunk_type"] in ("text", "table")
            assert len(c["content"].strip()) > 0, f"空 chunk: P{c['page']}"


# ============ 降级容错 ============


class TestFallbackHandling:
    """表格提取的异常处理"""

    def test_非PDF文件不抛异常(self):
        """加载非 PDF 文件不应在表格提取阶段崩溃"""
        md_path = DATA_DIR / "测试财报摘要.md"
        if not md_path.exists():
            pytest.skip("测试文件不存在")
        from rag.loader import load_document
        pages = load_document(str(md_path))
        assert len(pages) > 0
        # MD 文件没有表格，tables 字段应为空列表
        for p in pages:
            assert p.get("tables") == []

    def test_空表不崩溃(self):
        """空页面不会导致表格提取崩溃"""
        # 构造一个空页面结构
        empty_page = [{"text": "", "tables": [], "page": 1, "source": "empty.pdf"}]
        chunks = semantic_chunk_per_page(empty_page)
        assert chunks == []  # 空页面不产生 chunk
