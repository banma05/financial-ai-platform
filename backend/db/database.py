"""
数据库连接管理 — 环境变量驱动，SQLite(默认) → MySQL(设置 DATABASE_URL 即可)
"""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from loguru import logger

# V9.1: 环境变量驱动，SQLite → MySQL 无需改代码
DB_PATH = Path(__file__).parent.parent.parent / "data" / "platform.db"
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DB_URL else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库：创建所有表"""
    Base.metadata.create_all(bind=engine)
    logger.info(f"数据库已初始化: {DB_PATH}")
