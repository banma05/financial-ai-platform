"""
语义动态切分 — 不用固定 Token 一刀切

原理：
1. 先按段落/句子拆成原子单元
2. 计算相邻单元的语义相似度
3. 相似度陡降处 = 语义边界，在此切分
4. 保留 10%-20% 上下文重叠窗口，保语义完整

面试要点：仅这步就能提 15 个点的召回率
"""
from typing import List
import numpy as np
from loguru import logger


def _split_sentences(text: str) -> List[str]:
    """将文本拆分为句子级原子单元"""
    import re
    # 按中文标点拆分，保留标点
    sentences = re.split(r'(?<=[。！？；\n])(?![。！？；\n])', text)
    # 过滤空串和纯空白
    sentences = [s.strip() for s in sentences if s.strip()]
    # 合并过短的句子（< 20 字合并到下一句）
    merged = []
    buffer = ""
    for s in sentences:
        if len(buffer) + len(s) < 50 and buffer:
            buffer += s
        elif buffer:
            merged.append(buffer)
            buffer = s
        else:
            if len(s) < 20 and merged:
                merged[-1] += s
            else:
                merged.append(s)
    if buffer:
        merged.append(buffer)
    return merged


def semantic_chunk(
    text: str,
    min_chunk_size: int = 200,
    max_chunk_size: int = 1200,
    overlap_ratio: float = 0.15,
) -> List[str]:
    """
    基于语义相似度的动态分块

    参数:
        text: 原始文本
        min_chunk_size: 最小块大小（字符）
        max_chunk_size: 最大块大小（字符）
        overlap_ratio: 上下文重叠比例（10%-20%）

    返回:
        文本块列表
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    if len(sentences) <= 3:
        return [" ".join(sentences)]

    # 获取句子向量
    try:
        from .embedder import get_embedding_model
        model = get_embedding_model()
        embeddings = model.embed_documents(sentences)
        embeddings = np.array(embeddings)
    except Exception as e:
        logger.warning(f"语义切分降级为固定切分: {e}")
        return _fallback_chunk(text, max_chunk_size, overlap_ratio)

    # 计算相邻句子相似度，找语义断点
    similarities = []
    for i in range(len(embeddings) - 1):
        sim = np.dot(embeddings[i], embeddings[i + 1]) / (
            np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[i + 1]) + 1e-8
        )
        similarities.append(float(sim))

    # 动态阈值：均值 - 0.5*标准差（相似度显著低于平均处即断点）
    if similarities:
        mean_sim = np.mean(similarities)
        std_sim = np.std(similarities)
        threshold = mean_sim - 0.5 * std_sim
    else:
        threshold = 0.5

    # 在语义断点处切分
    chunks = []
    current_chunk = sentences[0]
    overlap_size = int(max_chunk_size * overlap_ratio)

    for i in range(1, len(sentences)):
        is_boundary = similarities[i - 1] < threshold
        would_overflow = len(current_chunk) + len(sentences[i]) > max_chunk_size
        too_small = len(current_chunk) < min_chunk_size

        if (is_boundary and not too_small) or would_overflow:
            chunks.append(current_chunk)
            # 上下文重叠：前一块的尾部作为下一块的开头
            if overlap_size > 0 and len(current_chunk) > overlap_size:
                current_chunk = current_chunk[-overlap_size:] + sentences[i]
            else:
                current_chunk = sentences[i]
        else:
            current_chunk += sentences[i]

    if current_chunk.strip():
        chunks.append(current_chunk)

    logger.info(
        f"语义切分: {len(sentences)} 句 → {len(chunks)} 块"
        f" (阈值={threshold:.3f}, 重叠={overlap_ratio:.0%})"
    )
    return chunks


def _fallback_chunk(text: str, chunk_size: int, overlap_ratio: float) -> List[str]:
    """降级方案：固定大小切分"""
    overlap = int(chunk_size * overlap_ratio)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks
