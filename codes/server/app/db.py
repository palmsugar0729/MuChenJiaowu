"""数据库连接。

SQLite 必须开的三条 PRAGMA：
- journal_mode=WAL    读写并发，避免「database is locked」
- foreign_keys=ON     SQLite 默认关闭外键，必须手动开
- busy_timeout=5000   写锁冲突时等 5 秒再报错
"""

from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=settings.sql_echo,
)


@event.listens_for(engine, "connect")
def _apply_sqlite_pragma(dbapi_connection, _connection_record) -> None:
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个 session。"""
    with Session(engine) as session:
        yield session


def init_db() -> None:
    """建表。已存在的表不会被改动。"""
    from app import models  # noqa: F401  —— 必须先导入，表才会注册进 metadata

    settings.ensure_data_dir()
    SQLModel.metadata.create_all(engine)
