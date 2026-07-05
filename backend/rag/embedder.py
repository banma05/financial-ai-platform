"""
向量化模块 - 将文本转为向量
使用本地 BGE 模型（免费），所有缓存指向 D 盘
"""
from pathlib import Path
from langchain_huggingface import HuggingFaceEmbeddings
from config import EMBEDDING_MODEL, LOCAL_MODEL_PATH, HF_HOME

_embedding_model = None


def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    获取 Embedding 模型（懒加载单例）

    bge-small-zh-v1.5 — BAAI 发布的中文 Embedding 模型：
    - ~100MB，已通过 ModelScope 下载到本地
    - 中文效果好，免费，数据不出本地
    """
    global _embedding_model
    if _embedding_model is None:
        # 优先使用本地已下载的模型路径
        model_path = LOCAL_MODEL_PATH
        if not Path(model_path).exists():
            model_path = EMBEDDING_MODEL  # 回退到 HuggingFace 在线下载
        # 🔧 GPU 加速：RTX4060 8GB，BGE ~400MB + CrossEncoder ~1.5GB 绰绰有余
        # CUDA 上下文由 hybrid_search 的 CrossEncoder(GPU) 预加载，不会 segfault
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _embedding_model = HuggingFaceEmbeddings(
            model_name=model_path,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True},
        )
    return _embedding_model
