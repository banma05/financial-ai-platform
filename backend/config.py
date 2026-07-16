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
AGENT_LLM_MODEL = os.getenv("AGENT_LLM_MODEL", "deepseek-v4-flash")
# Agent 模块（Planner/DataQuery）默认用 flash 提速，Reporter 洞察仍用 pro 保质量

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

# 语义切分参数
SEMANTIC_THRESHOLD_MODE = os.getenv("SEMANTIC_THRESHOLD_MODE", "mean-1std")
# 可选值: "mean-1std"（默认，保守切分，减少碎片）、"mean-0.5std"（更多切分）、"mean"（最保守）
# 对应 sigma_multiplier: 1.0 / 0.5 / 0.0
SEMANTIC_MIN_CHUNK_SIZE = int(os.getenv("SEMANTIC_MIN_CHUNK_SIZE", "400"))
SEMANTIC_MAX_CHUNK_SIZE = int(os.getenv("SEMANTIC_MAX_CHUNK_SIZE", "1500"))
SEMANTIC_OVERLAP_RATIO = float(os.getenv("SEMANTIC_OVERLAP_RATIO", "0.20"))

# ============ Query 处理参数 ============
QUERY_SHORT_THRESHOLD = int(os.getenv("QUERY_SHORT_THRESHOLD", "15"))
# 短 query 阈值（字符数），低于此值触发 LLM 扩写
QUERY_MIN_SIMILARITY = float(os.getenv("QUERY_MIN_SIMILARITY", "0.8"))
# 扩写后与原文余弦相似度最低阈值，低于此值废弃扩写，使用原文
# 调低（如 0.7）→ 更多扩写被接受（可能有噪声）
# 调高（如 0.85）→ 更多扩写被拒绝（可能丢失信息）

# ============ 检索参数 ============
RETRIEVAL_TOP_K = 5       # 检索返回的最相关文档数

# ============ API 安全配置 ============
API_KEY = os.getenv("API_KEY", "")
# API 鉴权密钥，为空时不启用鉴权（开发环境），生产环境必须设置
# 使用方式：请求头 X-API-Key: <API_KEY>

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
# 是否启用限流，默认开启。「true」开启，「false」关闭

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
# 每 IP 每分钟最大请求数（默认 30），chat/stream 接口单独控制

RATE_LIMIT_CHAT_PER_MINUTE = int(os.getenv("RATE_LIMIT_CHAT_PER_MINUTE", "10"))
# 每 IP 每分钟 chat/stream 最大请求数（默认 10，LLM 调用成本高）

# ============ Agent 配置（模块二）============
AGENT_MAX_TASKS = int(os.getenv("AGENT_MAX_TASKS", "5"))
# V8.2: 单次分析最多拆解的子任务数，从 10 降到 5（多数场景 3-5 个足够，减少 LLM 调用次数和延迟）

AGENT_TASK_TIMEOUT = float(os.getenv("AGENT_TASK_TIMEOUT", "15.0"))
# V8.2: 单个子任务超时（秒），从 30s 降到 15s，快速失败优于长时间等待

AGENT_TOTAL_TIMEOUT = float(os.getenv("AGENT_TOTAL_TIMEOUT", "45.0"))
# V8.2: Agent 总体超时（秒），超过此时间直接返回已完成部分

CHART_OUTPUT_DIR = os.getenv("CHART_OUTPUT_DIR", str(ROOT_DIR / "data" / "charts"))
# 图表输出目录（base64 模式不落盘，留作后续 PDF 导出用）
Path(CHART_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
