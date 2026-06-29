"""
文档加载器 - 支持 PDF / Word / Markdown / TXT
"""
from pathlib import Path
from typing import List
from loguru import logger
import pymupdf  # fitz


def load_pdf(file_path: str) -> List[dict]:
    """
    加载 PDF 文件，按页提取文本
    返回: [{"text": "...", "page": 1, "source": "xxx.pdf"}, ...]
    """
    docs = []
    try:
        doc = pymupdf.open(file_path)
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            if text.strip():
                docs.append({
                    "text": text.strip(),
                    "page": page_num,
                    "source": Path(file_path).name,
                })
        logger.info(f"PDF 加载完成: {file_path} -> {len(docs)} 页")
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
