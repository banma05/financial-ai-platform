"""
pytest 全局配置 — 将 backend 目录加入 Python path
"""
import sys
from pathlib import Path

# 将 backend 目录添加到 sys.path，使测试文件可以直接 import rag.xxx
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
