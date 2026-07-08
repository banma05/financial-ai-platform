"""
文档加载器 - 支持 PDF / Word / Markdown / TXT
"""
from pathlib import Path
from typing import List
from loguru import logger
import pymupdf  # fitz


def _table_to_markdown(pymupdf_table) -> str:
    """
    将 PyMuPDF Table 对象转为干净的 Markdown 表格。

    优先级：table.extract() → to_markdown() 兜底。
    extract() 对合并单元格的处理更好（重复值而非乱码 ColN）。
    """
    # ── 优先用 extract() 手动构建，避免 to_markdown() 的合并单元格乱码 ──
    try:
        data = pymupdf_table.extract()
        if data:
            lines = []
            for i, row in enumerate(data):
                cells = []
                for c in row:
                    cell_text = str(c).replace("\n", " ").replace("|", "/").strip() if c else ""
                    # 过滤 PyMuPDF 合并单元格生成的 ColN 占位符
                    if cell_text and not cell_text.startswith("Col"):
                        cells.append(cell_text)
                    else:
                        cells.append("")
                # 跳过全是 ColN 占位符的行
                if any(c for c in cells if c):
                    lines.append("| " + " | ".join(cells) + " |")
                    if i == 0:  # 表头分隔行
                        lines.append("|" + "|".join(["---"] * len(cells)) + "|")
            if len(lines) > 2:  # 至少有表头+分隔行+一行数据
                return "\n".join(lines)
    except Exception:
        pass

    # ── 兜底：to_markdown() ──
    try:
        md = pymupdf_table.to_markdown()
        md = md.replace("<br>", " ")
        # 清理 ColN 占位符（合并单元格残留）
        import re
        md = re.sub(r'\bCol\d+\b', '', md)
        return md
    except Exception:
        return ""


def load_pdf(file_path: str) -> List[dict]:
    """
    加载 PDF 文件，按页提取文本 + 结构化表格

    使用 "blocks" 模式提取文本：按版面段落块分组，保留阅读顺序
    （默认 get_text() 按物理坐标排序，多栏布局下会交叉拼接）

    返回: [{
        "text": "段落文本...",
        "tables": [{"markdown": "...", "rows": 5, "cols": 3}, ...],
        "page": 1,
        "source": "xxx.pdf"
    }, ...]
    """
    docs = []
    total_tables = 0
    try:
        doc = pymupdf.open(file_path)
        for page_num, page in enumerate(doc, start=1):
            # 用 "blocks" 模式按版面段落块提取，避免多栏乱序
            blocks = page.get_text("blocks")
            # 按 y 坐标为主、x 坐标为辅排序（先上后下，先左后右）
            blocks.sort(key=lambda b: (round(b[1] / 10) * 10, b[0]))
            # 只取文本块（type=0），过滤图片块
            text_lines = [b[4].strip() for b in blocks if b[4].strip() and b[6] == 0]
            text = "\n".join(text_lines)

            tables = []

            # 检测页面中的表格
            try:
                found = page.find_tables()
                for t in found.tables:
                    md = _table_to_markdown(t)
                    if md.strip():
                        tables.append({
                            "markdown": md,
                            "rows": t.row_count,
                            "cols": t.col_count,
                        })
                total_tables += len(tables)
            except Exception as e:
                logger.debug(f"表格检测失败 P{page_num}: {e}")

            # 保留非空页面（有文本或有表格）
            if text.strip() or tables:
                docs.append({
                    "text": text.strip(),
                    "tables": tables,
                    "page": page_num,
                    "source": Path(file_path).name,
                })

        logger.info(
            f"PDF 加载完成: {file_path} -> {len(docs)} 页, {total_tables} 张表格"
        )
    except Exception as e:
        logger.error(f"PDF 加载失败: {e}")
        raise
    return docs


def load_docx(file_path: str) -> List[dict]:
    """加载 Word 文档"""
    from docx import Document
    docs = []
    try:
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text.strip())
        if full_text:
            docs.append({
                "text": "\n".join(full_text),
                "tables": [],
                "page": 1,
                "source": Path(file_path).name,
            })
        logger.info(f"DOCX 加载完成: {file_path}")
    except Exception as e:
        logger.error(f"DOCX 加载失败: {e}")
        raise
    return docs


def load_markdown(file_path: str) -> List[dict]:
    """加载 Markdown 文件"""
    docs = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        if text.strip():
            docs.append({
                "text": text.strip(),
                "tables": [],
                "page": 1,
                "source": Path(file_path).name,
            })
        logger.info(f"Markdown 加载完成: {file_path}")
    except Exception as e:
        logger.error(f"Markdown 加载失败: {e}")
        raise
    return docs


def load_txt(file_path: str) -> List[dict]:
    """加载纯文本文件"""
    docs = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        if text.strip():
            docs.append({
                "text": text.strip(),
                "tables": [],
                "page": 1,
                "source": Path(file_path).name,
            })
    except UnicodeDecodeError:
        # 尝试 GBK 编码（常见于中文文档）
        with open(file_path, "r", encoding="gbk") as f:
            text = f.read()
        if text.strip():
            docs.append({
                "text": text.strip(),
                "tables": [],
                "page": 1,
                "source": Path(file_path).name,
            })
    return docs


def load_document(file_path: str) -> List[dict]:
    """
    根据文件类型自动选择加载器
    """
    ext = Path(file_path).suffix.lower()
    loaders = {
        ".pdf": load_pdf,
        ".docx": load_docx,
        ".doc": load_docx,
        ".md": load_markdown,
        ".txt": load_txt,
    }
    loader = loaders.get(ext)
    if not loader:
        raise ValueError(f"不支持的文件格式: {ext}，支持的格式: {list(loaders.keys())}")
    return loader(file_path)
