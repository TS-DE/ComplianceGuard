"""数据库会话：Engine + SessionLocal + FastAPI 依赖 get_db。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.core.config import settings

# 连接池参数：MySQL 默认 8 小时断开闲置连接，recycle 要比它短
POOL_RECYCLE_SECONDS = 3600

engine = create_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE_SECONDS,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """每个请求一个 Session，请求结束必定关闭。

    返回:
        Session 实例（由 FastAPI 依赖注入）
    异常:
        请求内抛出的异常会继续上抛给全局处理器，这里只负责回滚与关闭。
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
