"""
数据库连接管理 — SQLite（MVP）→ MySQL（生产切换：改连接串即可）
"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from loguru import logger

# 数据库文件路径：data/platform.db
DB_PATH = Path(__file__).parent.parent.parent / "data" / "platform.db"
DB_URL = f"sqlite:///{DB_PATH}"

# MySQL 切换方式（生产环境取消注释）：
# DB_URL = "mysql+pymysql://user:password@localhost:3306/financial_platform"

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
