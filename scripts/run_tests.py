"""
测试运行器 — 必须在 pytest 之前预导入 sentence_transformers 防止 CUDA segfault

根因: PyTorch 2.6+cu124 与 sentence-transformers 的 CUDA 初始化顺序冲突。
      langchain_huggingface 先于 CrossEncoder 初始化 sentence_transformers 全局状态时，
      后续 CrossEncoder(device='cuda') 会导致 Windows access violation。

修复: 在 import pytest 之前预导入 sentence_transformers，确保 CUDA 上下文正确初始化。

用法:
    python scripts/run_tests.py                           # 运行全部测试
    python scripts/run_tests.py backend/tests/test_agent_planner.py -v  # 指定测试
    python scripts/run_tests.py -k "test_financial" -v    # 关键字过滤
"""
import os
import sys
from pathlib import Path

# 🔧 环境变量：必须在所有 import 之前设置
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 🔧 预导入 sentence_transformers：必须在 import pytest 之前
# 否则 pytest 插件链可能先触发 langchain → sentence_transformers 的错误初始化路径
import sentence_transformers  # noqa: E402, F401

# 将 backend 目录加入 Python path
_backend_dir = Path(__file__).parent.parent / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import pytest  # noqa: E402

if __name__ == "__main__":
    # 默认运行全部测试，可通过命令行参数覆盖
    args = sys.argv[1:] if len(sys.argv) > 1 else ["backend/tests/", "-v"]
    sys.exit(pytest.main(args))
