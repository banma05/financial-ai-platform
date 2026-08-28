"""
pytest 全局配置 — 将 backend 目录加入 Python path
V9.1: 自动初始化 DI Container（重依赖不可用时优雅降级）

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
# CI 环境可能没有重依赖（langchain_huggingface/chromadb/sentence_transformers），
# 此时 register_all() 会因导入失败而报错。优雅降级：跳过 Container 初始化，
# 依赖测试自身的 mock/fixture 来提供所需组件。
_container_available = False
try:
    from di import register_all, Container
    _container_available = True
except ImportError:
    pass  # CI 轻量模式：无重 ML 依赖


@pytest.fixture(autouse=True)
def _ensure_container_registered():
    """每个测试前确保 Container 工厂已注册（幂等，重依赖不可用时跳过）"""
    if _container_available and not Container.list_all():
        # 容器为空说明被 reset() 清空过（如 test_container 的隔离测试）。
        # 此时模块已在 sys.modules 缓存，register_all() 默认 __import__ 不会
        # 重新触发模块顶层自注册，必须 force=True 强制 reload 已加载模块。
        register_all(force=True)
    yield


@pytest.fixture
def reset_container():
    """需要隔离的测试使用此 fixture — 重置所有实例后重新注册"""
    if not _container_available:
        pytest.skip("Container 不可用（缺少重依赖）")
    Container.reset()
    register_all()
    yield
    Container.reset()
    register_all()
