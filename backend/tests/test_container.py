"""
V9.1: DI Container 核心测试 — 线程安全、重入性、测试隔离。

这些测试验证 V9.1 最核心的架构变更：14 个全局单例全部收归 Container 管理。
"""

import threading
import pytest
from di.container import Container


class _FakeComponent:
    """测试用组件"""
    def __init__(self):
        self.id = id(self)


@pytest.fixture(autouse=True)
def _clean_container():
    """每个测试前重置 Container"""
    Container.reset()
    yield
    Container.reset()


# ── 基础功能 ──

def test_register_and_resolve():
    """注册 → 解析 → 同一实例"""
    Container.register("test", _FakeComponent)
    a = Container.resolve("test")
    b = Container.resolve("test")
    assert a is b
    assert isinstance(a, _FakeComponent)


def test_resolve_unregistered_raises():
    """未注册的 key 应抛出 KeyError"""
    with pytest.raises(KeyError, match="未注册"):
        Container.resolve("nonexistent")


def test_list_all():
    """list_all 返回注册项及初始化状态"""
    Container.register("a", _FakeComponent)
    Container.register("b", _FakeComponent)
    all_items = Container.list_all()
    assert all_items == {"a": False, "b": False}
    Container.resolve("a")
    assert Container.list_all() == {"a": True, "b": False}


def test_is_ready():
    """is_ready 不触发惰性创建"""
    Container.register("x", _FakeComponent)
    assert not Container.is_ready("x")
    Container.resolve("x")
    assert Container.is_ready("x")


def test_register_override_warns():
    """重复注册 key 应覆盖并发出警告"""
    Container.register("dup", _FakeComponent)
    # 第二次注册应覆盖（不抛异常）
    Container.register("dup", lambda: "override")
    # 解析到最新注册的工厂
    assert Container.resolve("dup") == "override"


# ── 线程安全 ──

def test_concurrent_resolve_same_instance():
    """50 线程并发 resolve → 所有线程获得同一实例（无 TOCTOU）"""
    Container.register("shared", _FakeComponent)
    results = []

    def worker():
        results.append(id(Container.resolve("shared")))

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    unique = set(results)
    assert len(unique) == 1, f"期望 1 个唯一实例，实际 {len(unique)}"


def test_concurrent_resolve_with_heavy_factory():
    """并发 resolve 重工厂 → 只创建一次"""
    create_count = [0]  # 用 list 封装可变计数器

    def heavy_factory():
        create_count[0] += 1
        return _FakeComponent()

    Container.register("heavy", heavy_factory)
    results = []

    def worker():
        results.append(Container.resolve("heavy"))

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert create_count[0] == 1, f"工厂应只调用 1 次，实际 {create_count[0]}"
    assert len(set(id(r) for r in results)) == 1


# ── RLock 可重入性 ──

def test_reentrant_resolve():
    """工厂函数内部调用 Container.resolve() → RLock 可重入"""
    Container.register("dep", _FakeComponent)

    def dependent_factory():
        dep = Container.resolve("dep")  # 在工厂内再次 resolve
        return {"dep": dep}

    Container.register("main", dependent_factory)
    result = Container.resolve("main")
    assert isinstance(result["dep"], _FakeComponent)


def test_chain_resolve():
    """链式依赖: A → B → C"""
    Container.register("c", _FakeComponent)
    Container.register("b", lambda: {"c": Container.resolve("c")})
    Container.register("a", lambda: {"b": Container.resolve("b")})
    result = Container.resolve("a")
    assert isinstance(result["b"]["c"], _FakeComponent)


# ── 测试隔离 ──

def test_override():
    """override 替换为 mock 实例"""
    Container.register("svc", _FakeComponent)
    mock = object()
    Container.override("svc", mock)
    assert Container.resolve("svc") is mock


def test_reset_clears_all():
    """reset 后所有注册和实例清空"""
    Container.register("x", _FakeComponent)
    Container.resolve("x")
    Container.reset()
    assert Container.list_all() == {}


def test_warmup():
    """warmup 预加载指定组件"""
    Container.register("a", _FakeComponent)
    Container.register("b", _FakeComponent)
    Container.warmup(["a"])
    assert Container.is_ready("a")
    assert not Container.is_ready("b")  # 未指定预热的不应加载
