"""缓存后端测试."""

import pytest
from trip_planner.cache import NullCache, cache_key


@pytest.fixture
def cache():
    return NullCache()


@pytest.mark.asyncio
class TestNullCache:
    async def test_get_returns_none(self, cache):
        val = await cache.get("nonexistent")
        assert val is None

    async def test_set_and_get(self, cache):
        await cache.set("key", "value", 60)
        val = await cache.get("key")
        assert val is None  # NullCache always returns None

    async def test_delete(self, cache):
        await cache.delete("key")  # should not raise

    async def test_exists(self, cache):
        assert await cache.exists("key") is False


class TestCacheKey:
    def test_simple_key(self):
        assert cache_key("amap:weather", "北京") == "amap:weather:北京"

    def test_long_key_hashed(self):
        long_part = "a" * 200
        key = cache_key("test", long_part)
        assert key.startswith("test:")
        assert len(key) < 150  # 被 md5 缩短

    def test_multiple_parts(self):
        key = cache_key("amap:poi", "abc123")
        assert key == "amap:poi:abc123"
