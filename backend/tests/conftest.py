"""
pytest 全局配置 — 将 backend 目录加入 Python path
V9.1: 自动初始化 DI Container

注意：CUDA segfault 修复不在本文件（pytest 插件先于 conftest 加载），
      请使用 scripts/run_tests.py 运行测试。
"""
import sys
import pytest
from pathlib import Path

# 将 backend 目录添加到 sys.path，使测试文件可以直接 import rag.xxx
_backend_dir = Path(__file__).parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# ── V9.1: 确保 Container 在测试前已注册（幂等）──
from di import register_all, Container


@pytest.fixture(autouse=True)
def _ensure_container_registered():
    """每个测试前确保 Container 工厂已注册（幂等，重复调用不重复注册）"""
    if not Container.list_all():
        register_all()
    yield


@pytest.fixture
def reset_container():
    """需要隔离的测试使用此 fixture — 重置所有实例后重新注册"""
    Container.reset()
    register_all()
    yield
    Container.reset()
    register_all()
