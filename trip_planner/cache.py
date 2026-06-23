"""缓存后端抽象 — 支持 RedisCache / NullCache 两级降级."""

from abc import ABC, abstractmethod
from hashlib import md5
from typing import Optional


class CacheBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        ...

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int) -> None:
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        ...


class NullCache(CacheBackend):
    """Redis 不可用时的静默降级 — 所有操作 no-op."""

    async def get(self, key: str) -> Optional[str]:
        return None

    async def set(self, key: str, value: str, ttl: int) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass

    async def exists(self, key: str) -> bool:
        return False


class RedisCache(CacheBackend):
    """基于 redis-py async 的缓存实现."""

    def __init__(self, redis_url: str):
        import redis.asyncio as aioredis

        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url, decode_responses=True
        )

    async def get(self, key: str) -> Optional[str]:
        val = await self._redis.get(key)
        return val

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis.setex(key, ttl, value)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self._redis.exists(key))


def make_cache_backend(redis_url: Optional[str], enabled: bool = True) -> CacheBackend:
    """工厂函数 — 根据配置决定返回 RedisCache 或 NullCache."""
    if not enabled or not redis_url:
        return NullCache()
    try:
        return RedisCache(redis_url)
    except Exception as e:
        print(f"  Redis 连接失败, 降级为 NullCache: {e}")
        return NullCache()


def cache_key(prefix: str, *parts: str) -> str:
    """生成带前缀的缓存键, 长 parts 自动 md5 摘要."""
    raw = ":".join(parts)
    if len(raw) > 120:
        raw = md5(raw.encode()).hexdigest()
    return f"{prefix}:{raw}"
