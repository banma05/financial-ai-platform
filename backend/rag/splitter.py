"""
文本分割器 - 将长文档切分为适合检索的文本块
"""
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import CHUNK_SIZE, CHUNK_OVERLAP


# 财务文档专用分隔符
FINANCIAL_SEPARATORS = [
    "\n\n",     # 段落
    "\n",       # 换行
    "。",       # 中文句号
    "；",       # 中文分号
    "，",       # 中文逗号
    ".",        # 英文句号
    ";",        # 英文分号
    " ",        # 空格
    "",         # 字符级别
]


def create_text_splitter(
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> RecursiveCharacterTextSplitter:
    """
    创建针对财务文档优化的文本分割器
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=FINANCIAL_SEPARATORS,
        length_function=len,
        is_separator_regex=False,
    )


def split_documents(
    pages: List[dict],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[dict]:
    """
    将文档页拆分为文本块

    参数:
        pages: [{"text": "...", "page": 1, "source": "xxx.pdf"}, ...]

    返回:
        [{"content": "...", "page": 1, "source": "xxx.pdf"}, ...]
    """
    splitter = create_text_splitter(chunk_size, chunk_overlap)
    chunks = []

    for page in pages:
        # 对每页进行分块
        page_chunks = splitter.split_text(page["text"])
        for chunk_text in page_chunks:
            chunks.append({
                "content": chunk_text,
                "source": page["source"],
                "page": page["page"],
            })

    return chunks
