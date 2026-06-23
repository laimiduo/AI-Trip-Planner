"""FastAPI Depends 工厂 — 缓存 / 数据库 / 配置."""

from functools import lru_cache
from typing import AsyncGenerator

from fastapi import Request

from trip_planner.cache import CacheBackend, NullCache, make_cache_backend
from trip_planner.config import Settings


@lru_cache
def _global_cache(settings: Settings) -> CacheBackend:
    return make_cache_backend(settings.REDIS_URL, settings.ENABLE_CACHE)


def get_cache(request: Request) -> CacheBackend:
    """从 Request.state 获取缓存实例 (由 lifespan 注入)."""
    cache = getattr(request.app.state, "cache", None)
    return cache or NullCache()


async def get_db_session(request: Request) -> AsyncGenerator:
    """获取数据库 session (由 lifespan 初始化)."""
    from trip_planner.database import get_session

    async for session in get_session():
        yield session
