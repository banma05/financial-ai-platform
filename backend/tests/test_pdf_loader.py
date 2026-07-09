"""
PDF Loader 文本提取质量测试 — V8.0

验证修复后的 loader 输出：
1. 不含页码（纯数字行）
2. 不含页眉页脚垃圾
3. 正文段落完整
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from rag.loader import load_pdf


@pytest.fixture
def sample_pdf():
    """使用茅台2024年报作为测试样本"""
    pdf_path = Path(__file__).parent.parent.parent / "data" / "documents" / "贵州茅台2024年年报.pdf"
    if not pdf_path.exists():
        pytest.skip("测试需要 贵州茅台2024年年报.pdf")
    return str(pdf_path)


def test_load_pdf_returns_pages(sample_pdf):
    """基础：能正常加载PDF并返回页面"""
    pages = load_pdf(sample_pdf)
    assert len(pages) > 0, "至少加载到一页"
    assert all("text" in p for p in pages), "每页应有text字段"
    assert all("page" in p for p in pages), "每页应有page字段"


def test_text_no_page_numbers(sample_pdf):
    """文本中不应包含独立的页码"""
    pages = load_pdf(sample_pdf)
    for page in pages[:10]:  # 检查前10页
        lines = page["text"].split("\n")
        for line in lines:
            stripped = line.strip()
            # 纯数字且长度≤3的是页码
            if stripped.isdigit() and len(stripped) <= 3:
                # 排除：财务报表中的数值行（如"营业收入 1,741.44亿"）
                # 真正的页码是独立一行的纯数字
                if len(lines) > 1:
                    idx = lines.index(line)
                    # 页码通常在一页的最后
                    is_last = (idx == len(lines) - 1)
                    is_first = (idx == 0)
                    if (is_last or is_first) and len(stripped) <= 3:
                        pytest.fail(
                            f"第{page['page']}页发现疑似页码: '{stripped}' "
                            f"(位置: {'页首' if is_first else '页尾'})"
                        )


def test_text_no_header_footer_noise(sample_pdf):
    """文本不应包含明显的页眉/页脚噪音"""
    noise_patterns = [
        "年度报告",  # 页眉常见
    ]
    pages = load_pdf(sample_pdf)
    # 检查：大部分页面的第一行不应该是"年度报告"这种页眉
    header_count = 0
    for page in pages[:20]:
        first_line = page["text"].strip().split("\n")[0] if page["text"].strip() else ""
        if any(p in first_line for p in noise_patterns) and len(first_line) < 30:
            header_count += 1
    # 允许少量（目录页），但不应该多数页面都有
    assert header_count < 5, f"疑似页眉噪音过多: {header_count}/20页"


def test_text_has_meaningful_content(sample_pdf):
    """文本应该包含有意义的财务内容"""
    pages = load_pdf(sample_pdf)
    # 取中间的正文页（跳过封面/目录）
    mid_pages = pages[5:15]
    total_chars = sum(len(p["text"]) for p in mid_pages)
    assert total_chars > 5000, f"10页正文文本过少: {total_chars}字"


def test_tables_detected(sample_pdf):
    """表格检测应正常工作"""
    pages = load_pdf(sample_pdf)
    total_tables = sum(len(p.get("tables", [])) for p in pages)
    assert total_tables > 0, "茅台年报应能检测到表格"


def test_text_not_full_of_garbage_chars(sample_pdf):
    """文本不应全是乱码/ColN占位符"""
    pages = load_pdf(sample_pdf)
    for page in pages[3:8]:  # 跳过前几页封面
        text = page["text"]
        # ColN占位符
        import re
        col_patterns = re.findall(r'\bCol\d+\b', text)
        assert len(col_patterns) < 3, (
            f"第{page['page']}页发现{len(col_patterns)}个ColN占位符, "
            f"内容预览: {text[:200]}"
        )


def test_text_not_broken_sentences(sample_pdf):
    """文本不应该严重断句（每段平均长度应合理）"""
    pages = load_pdf(sample_pdf)
    short_line_count = 0
    total_lines = 0
    for page in pages[5:20]:
        lines = page["text"].split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) < 15:
                short_line_count += 1
            total_lines += 1
    # 短行比例过高说明文本被切得太碎
    ratio = short_line_count / max(total_lines, 1)
    assert ratio < 0.5, f"短行比例过高: {short_line_count}/{total_lines} = {ratio:.0%}"
