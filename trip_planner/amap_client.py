"""高德地图 Web Service API 直连客户端 — 可选缓存层."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from hashlib import md5
from typing import Optional

import httpx
from env_utils import AMAP_API_KEY
from trip_planner.cache import CacheBackend, NullCache, cache_key

AMAP_BASE = "https://restapi.amap.com/v3"


class AmapClient:
    """封装高德 REST API 的异步 HTTP 调用，支持缓存降级."""

    def __init__(self, cache: Optional[CacheBackend] = None):
        self.api_key = AMAP_API_KEY
        self.cache = cache or NullCache()

    async def search_poi(
        self, keywords: str, city: str, types: str = "", offset: int = 20
    ) -> list[dict]:
        """POI 文本搜索 (缓存 24h)."""
        raw = f"{keywords}:{city}:{types}:{offset}"
        key = cache_key("amap:poi", md5(raw.encode()).hexdigest())

        cached = await self.cache.get(key)
        if cached is not None:
            return json.loads(cached)

        params = {"key": self.api_key, "keywords": keywords, "city": city, "offset": offset, "extensions": "all"}
        if types:
            params["types"] = types
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AMAP_BASE}/place/text", params=params)
            data = resp.json()
            if data.get("status") == "1":
                pois = data.get("pois", [])
                await self.cache.set(key, json.dumps(pois), 86400)  # 24h
                return pois
            raise RuntimeError(f"高德 POI 搜索失败: {data.get('info', 'unknown')}")

    async def get_weather(self, city: str) -> dict:
        """天气预报查询 (缓存 30min)."""
        key = cache_key("amap:weather", city)

        cached = await self.cache.get(key)
        if cached is not None:
            return json.loads(cached)

        params = {"key": self.api_key, "city": city, "extensions": "all"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AMAP_BASE}/weather/weatherInfo", params=params)
            data = resp.json()
            if data.get("status") == "1":
                forecasts = data.get("forecasts", [])
                result = forecasts[0] if forecasts else {}
                await self.cache.set(key, json.dumps(result), 1800)  # 30min
                return result
            raise RuntimeError(f"高德天气查询失败: {data.get('info', 'unknown')}")

    async def get_geocode(self, address: str, city: str = "") -> dict | None:
        """地理编码: 地址 → 经纬度 (缓存 7天)."""
        raw = f"{address}:{city}"
        key = cache_key("amap:geocode", md5(raw.encode()).hexdigest())

        cached = await self.cache.get(key)
        if cached is not None:
            return json.loads(cached)

        params = {"key": self.api_key, "address": address, "city": city}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AMAP_BASE}/geocode/geo", params=params)
            data = resp.json()
            if data.get("status") == "1" and data.get("geocodes"):
                result = data["geocodes"][0]
                await self.cache.set(key, json.dumps(result), 604800)  # 7天
                return result
            return None

    async def get_driving_distance(self, origin: str, destination: str) -> dict | None:
        """驾车路线规划 (缓存 1h)."""
        key = cache_key("amap:driving", f"{origin}:{destination}")

        cached = await self.cache.get(key)
        if cached is not None:
            return json.loads(cached)

        params = {
            "key": self.api_key,
            "origin": origin,
            "destination": destination,
            "strategy": "0",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AMAP_BASE}/direction/driving", params=params)
            data = resp.json()
            if data.get("status") == "1" and data.get("route"):
                paths = data["route"].get("paths", [])
                result = paths[0] if paths else None
                if result:
                    await self.cache.set(key, json.dumps(result), 3600)  # 1h
                return result
            return None
