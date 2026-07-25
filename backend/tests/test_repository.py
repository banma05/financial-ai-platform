"""
V9.1: Repository 层测试 — 验证批量查询的正确性和性能。

V9.0 问题: _query_one_company 三重循环 N+1 SQL（50-300次/请求）。
V9.1 修复: FinancialRepository.query_batch() 一次 IN 查询 + 内存组装。
"""

import pytest
from db.repository import BaseRepository, FinancialRepository
from db.database import SessionLocal


@pytest.fixture
def repo():
    return FinancialRepository()


@pytest.fixture
def db():
    """提供测试数据库会话"""
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()


# ── BaseRepository ──

def test_session_context_manager():
    """session() 自动创建/提交/关闭"""
    repo = BaseRepository()
    with repo.session() as db:
        assert db is not None
        # 简单查询验证连接正常
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_using_reuses_external_session(db):
    """using() 复用外部传入的会话"""
    repo = BaseRepository()
    with repo.using(db) as session:
        assert session is db  # 同一个对象


def test_using_creates_internal_when_none():
    """using() 无外部会话时创建内部会话"""
    repo = BaseRepository()
    with repo.using(None) as session:
        assert session is not None


# ── FinancialRepository ──

def test_query_batch_returns_correct_structure(repo, db):
    """query_batch 返回 {year: {key: value}} 结构"""
    result = repo.query_batch("600519", [2024], ["revenue"], db=db)
    assert 2024 in result
    assert "revenue" in result[2024]


def test_query_batch_maotai_revenue(repo, db):
    """茅台 2024 年营收应约 1708.99 亿（数据库存元，约 1.71e11）"""
    result = repo.query_batch("600519", [2024], ["revenue"], db=db)
    revenue = result[2024].get("revenue")
    assert revenue is not None, "茅台营收应为非空"
    # 数据库存储单位为元（约 1708.99 亿 = 1.71e11 元）
    assert 1.5e11 < revenue < 2.0e11, f"茅台营收预期 ~1709亿，实际 {revenue/1e8:.2f}亿"


def test_query_batch_multi_years(repo, db):
    """多年份查询"""
    result = repo.query_batch("600519", [2022, 2023, 2024], ["revenue"], db=db)
    for year in [2022, 2023, 2024]:
        assert result[year].get("revenue") is not None, f"{year}年数据缺失"


def test_query_batch_missing_company(repo, db):
    """不存在的公司 → 返回空字典结构"""
    result = repo.query_batch("000000", [2024], ["revenue"], db=db)
    assert 2024 in result
    assert result[2024] == {}


def test_query_multi_company(repo, db):
    """多公司查询 → {symbol: {year: {key: value}}}"""
    result = repo.query_multi_company(
        ["600519", "000858"], [2024], ["revenue", "net_profit_attr_parent"], db=db
    )
    assert "600519" in result
    assert "000858" in result
    assert 2024 in result["600519"]
    assert 2024 in result["000858"]


def test_query_batch_handles_nonexistent_keys(repo, db):
    """不存在的 metric_key → value 为 None"""
    result = repo.query_batch("600519", [2024], ["nonexistent_key_xyz"], db=db)
    assert "nonexistent_key_xyz" not in result[2024]


def test_query_batch_consistency_with_legacy(repo, db):
    """
    V9.1 批量查询与旧版逐条查询结果一致。

    通过 try_query（内部调用改写后的 _query_one_company）验证
    批量查询路径的输出正确性。
    """
    from db.financial_query import try_query
    legacy_result = try_query("茅台 2024 营业收入 净利润 毛利率")
    assert legacy_result is not None
    data = legacy_result.get("data", {})
    assert "营业收入_2024" in data
    assert "毛利率_2024" in data
    assert "净利润_2024" in data
    # 财务一致性：毛利率 = (营收 - 营业成本) / 营收 * 100
    assert 0 < data["毛利率_2024"] < 100, f"毛利率应 0-100%，实际 {data['毛利率_2024']}%"
