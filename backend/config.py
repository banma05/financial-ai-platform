"""
智能财务分析平台 - 全局配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.resolve()

# ============ DeepSeek API 配置 ============
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-pro")

# ============ 模型缓存全部指向 D 盘，不占 C 盘 ============
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
HF_HOME = os.getenv("HF_HOME", "D:/Python312/huggingface-cache")
MODELSCOPE_CACHE = os.getenv("MODELSCOPE_CACHE", "D:/Python312/modelscope-cache")

os.environ.setdefault("HF_ENDPOINT", HF_ENDPOINT)
os.environ.setdefault("HF_HOME", HF_HOME)
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", HF_HOME)
os.environ.setdefault("MODELSCOPE_CACHE", MODELSCOPE_CACHE)

# 确保缓存目录存在
Path(HF_HOME).mkdir(parents=True, exist_ok=True)
Path(MODELSCOPE_CACHE).mkdir(parents=True, exist_ok=True)

# ============ Embedding 模型 ============
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
# 本地模型路径（优先使用，已通过 ModelScope 下载，升级到 bge-base：768维 vs 原来 512维）
LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH", str(ROOT_DIR / "data" / "models" / "BAAI" / "bge-base-zh-v1___5"))

# ============ ChromaDB ============
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", str(ROOT_DIR / "data" / "chroma_db"))

# ============ 文件上传 ============
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(ROOT_DIR / "data" / "documents")))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

# 确保目录存在
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)

# ============ 分块参数 ============
CHUNK_SIZE = 800          # 每个文本块的大小（字符数）
CHUNK_OVERLAP = 150       # 块之间的重叠（保证语义连贯）

# ============ 检索参数 ============
RETRIEVAL_TOP_K = 5       # 检索返回的最相关文档数
