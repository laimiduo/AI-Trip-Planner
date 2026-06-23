"""SQLAlchemy 2.0 async engine + session 工厂."""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from trip_planner.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_async_session_maker = None


def get_database_url(database_url: Optional[str] = None) -> Optional[str]:
    """补全 async driver; 如果是 postgresql:// 自动替换为 postgresql+asyncpg://."""
    url = database_url or get_settings().DATABASE_URL
    if not url:
        return None
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def init_db(database_url: Optional[str] = None) -> None:
    """初始化全局 engine + session maker."""
    global _engine, _async_session_maker
    url = get_database_url(database_url)
    if not url:
        print("  DATABASE_URL 未配置, DB 功能禁用")
        return
    _engine = create_async_engine(url, echo=False, pool_size=5, max_overflow=10)
    _async_session_maker = async_sessionmaker(_engine, expire_on_commit=False)


async def close_db() -> None:
    """关闭数据库连接池."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends 用 — 自动管理 session 生命周期."""
    if _async_session_maker is None:
        raise RuntimeError("数据库未初始化, 请先调用 init_db()")
    async with _async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables() -> None:
    """创建所有未创建的表 (开发/测试用, 生产用 Alembic)."""
    if _engine is None:
        return
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def is_db_ready() -> bool:
    return _engine is not None
