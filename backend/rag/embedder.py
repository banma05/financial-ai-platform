"""
向量化模块 - 将文本转为向量
使用本地 BGE 模型（免费），所有缓存指向 D 盘

V9.1: 委托给 di.Container 管理单例生命周期（消除全局变量+锁）。
      保留 get_embedding_model() 作为兼容层，内部调用 Container.resolve()。
"""
from pathlib import Path
from langchain_huggingface import HuggingFaceEmbeddings
from config import EMBEDDING_MODEL, LOCAL_MODEL_PATH, HF_HOME
from di.container import Container


def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    获取 Embedding 模型（V9.1: 委托给 Container）。
    """
    return Container.resolve("embedding_model")


def _create_embedding_model() -> HuggingFaceEmbeddings:
    """
    工厂函数 — 供 Container 惰性初始化调用。

    bge-base-zh-v1.5 — BAAI 发布的中文 Embedding 模型：
    - 768维，~400MB
    - 中文效果好，免费，数据不出本地
    """
    model_path = LOCAL_MODEL_PATH
    if not Path(model_path).exists():
        model_path = EMBEDDING_MODEL

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"

    return HuggingFaceEmbeddings(
        model_name=model_path,
        model_kwargs={"device": device},
        encode_kwargs={"normalize_embeddings": True},
    )
