"""
向量化模块 - 将文本转为向量
使用本地模型（免费，不需要调 API）
"""
from langchain_huggingface import HuggingFaceEmbeddings
from config import EMBEDDING_MODEL

# 全局单例，避免重复加载模型
_embedding_model = None


def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    获取 Embedding 模型（懒加载单例）

    bge-small-zh-v1.5 是 BAAI 发布的中文 Embedding 模型：
    - 模型小（~100MB），首次会自动下载
    - 中文效果好
    - 免费，本地运行
    """
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},  # L2归一化，提高相似度计算精度
        )
    return _embedding_model
