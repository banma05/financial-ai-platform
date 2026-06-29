"""
语义动态切分（保页码版）

在每页内部做语义边界检测，保留页码溯源能力。
设计要点：不用固定Token一刀切，语义陡降处切分，可提升召回率
"""
from typing import List
import numpy as np
from loguru import logger


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
    min_chunk_size: int = 200,
    max_chunk_size: int = 1200,
    overlap_ratio: float = 0.15,
) -> List[dict]:
    """
    在每页内做语义动态切分，保留页码信息

    参数:
        pages: [{"text": "...", "page": 1, "source": "xxx.pdf"}, ...]
        min_chunk_size: 最小块大小
        max_chunk_size: 最大块大小
        overlap_ratio: 上下文重叠比例（10%-20%）

    返回:
        [{"content": "...", "source": "xxx.pdf", "page": 1}, ...]
    """
    from .embedder import get_embedding_model

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
        threshold = mean_sim - 0.5 * std_sim  # 相似度陡降处 = 语义边界

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

    logger.info(f"语义切分: {len(pages)}页 → {len(all_chunks)}块 (重叠={overlap_ratio:.0%})")
    return all_chunks
