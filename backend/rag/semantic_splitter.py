"""
语义动态切分（保页码版）

在每页内部做语义边界检测，保留页码溯源能力。
设计要点：不用固定Token一刀切，语义陡降处切分，可提升召回率
"""
from typing import List
import numpy as np
from loguru import logger

# 从 config 读取阈值模式
from config import (
    SEMANTIC_THRESHOLD_MODE,
    SEMANTIC_MIN_CHUNK_SIZE,
    SEMANTIC_MAX_CHUNK_SIZE,
    SEMANTIC_OVERLAP_RATIO,
)

# 阈值模式 → sigma 倍率映射
_THRESHOLD_SIGMA_MAP = {
    "mean-1std": 1.0,
    "mean-0.5std": 0.5,
    "mean": 0.0,
}


def _get_threshold_sigma() -> float:
    """获取当前配置的语义阈值 sigma 倍率"""
    sigma = _THRESHOLD_SIGMA_MAP.get(SEMANTIC_THRESHOLD_MODE)
    if sigma is None:
        logger.warning(f"未知语义阈值模式 '{SEMANTIC_THRESHOLD_MODE}'，回退为 mean-0.5std")
        sigma = 0.5
    return sigma


def _split_sentences(text: str) -> List[str]:
    import re
    sentences = re.split(r'(?<=[。！？；\n])(?![。！？；\n])', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    merged = []
    for s in sentences:
        if merged and len(s) < 20:
            merged[-1] += s
        else:
            merged.append(s)
    return merged


def semantic_chunk_per_page(
    pages: List[dict],
    min_chunk_size: int = None,
    max_chunk_size: int = None,
    overlap_ratio: float = None,
    sigma_mul: float = None,
) -> List[dict]:
    """
    在每页内做语义动态切分，保留页码信息

    参数:
        pages: [{"text": "...", "page": 1, "source": "xxx.pdf"}, ...]
        min_chunk_size: 最小块大小（默认从 config 读取）
        max_chunk_size: 最大块大小（默认从 config 读取）
        overlap_ratio: 上下文重叠比例 10%-20%（默认从 config 读取）
        sigma_mul: 语义阈值 sigma 倍率（默认从 config 读取：1.0/0.5/0.0）

    返回:
        [{"content": "...", "source": "xxx.pdf", "page": 1}, ...]
    """
    from .embedder import get_embedding_model

    # 使用传入参数或 config 默认值
    if min_chunk_size is None:
        min_chunk_size = SEMANTIC_MIN_CHUNK_SIZE
    if max_chunk_size is None:
        max_chunk_size = SEMANTIC_MAX_CHUNK_SIZE
    if overlap_ratio is None:
        overlap_ratio = SEMANTIC_OVERLAP_RATIO
    if sigma_mul is None:
        sigma_mul = _get_threshold_sigma()

    all_chunks = []
    model = get_embedding_model()
    overlap_size = int(max_chunk_size * overlap_ratio)

    for page in pages:
        text = page["text"]
        sentences = _split_sentences(text)

        # 短页不切
        if len(text) < max_chunk_size or len(sentences) <= 2:
            if text.strip():
                all_chunks.append({
                    "content": text.strip(),
                    "source": page["source"],
                    "page": page["page"],
                })
            continue

        # 句子级语义边界检测
        try:
            embeddings = model.embed_documents(sentences)
            embeddings = np.array(embeddings)
        except Exception:
            # 降级：固定切分
            for i in range(0, len(text), max_chunk_size - overlap_size):
                chunk = text[i:i + max_chunk_size]
                if chunk.strip():
                    all_chunks.append({
                        "content": chunk.strip(),
                        "source": page["source"],
                        "page": page["page"],
                    })
            continue

        # 计算相邻句子相似度
        sims = []
        for i in range(len(embeddings) - 1):
            sim = float(np.dot(embeddings[i], embeddings[i + 1]) /
                        (np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[i + 1]) + 1e-8))
            sims.append(sim)

        mean_sim = np.mean(sims) if sims else 0.5
        std_sim = np.std(sims) if sims else 0.1
        threshold = mean_sim - sigma_mul * std_sim  # 相似度陡降处 = 语义边界

        # 聚合
        current = sentences[0]
        for i in range(1, len(sentences)):
            is_boundary = sims[i - 1] < threshold
            would_overflow = len(current) + len(sentences[i]) > max_chunk_size
            too_small = len(current) < min_chunk_size

            if (is_boundary and not too_small) or would_overflow:
                if current.strip():
                    all_chunks.append({
                        "content": current.strip(),
                        "source": page["source"],
                        "page": page["page"],
                    })
                # 重叠窗口
                if overlap_size > 0 and len(current) > overlap_size:
                    current = current[-overlap_size:] + sentences[i]
                else:
                    current = sentences[i]
            else:
                current += sentences[i]

        if current.strip():
            all_chunks.append({
                "content": current.strip(),
                "source": page["source"],
                "page": page["page"],
            })

    logger.info(
        f"语义切分: {len(pages)}页 → {len(all_chunks)}块 "
        f"(重叠={overlap_ratio:.0%}, sigma_mul={sigma_mul}, 模式={SEMANTIC_THRESHOLD_MODE})"
    )
    return all_chunks
