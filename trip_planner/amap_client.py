"""高德地图 Web Service API 直连客户端 — 无需 MCP / LLM 中介"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from env_utils import AMAP_API_KEY

AMAP_BASE = "https://restapi.amap.com/v3"


class AmapClient:
    """封装高德 REST API 的异步 HTTP 调用."""

    def __init__(self):
        self.api_key = AMAP_API_KEY

    async def search_poi(
        self, keywords: str, city: str, types: str = "", offset: int = 20
    ) -> list[dict]:
        """POI 文本搜索."""
        params = {"key": self.api_key, "keywords": keywords, "city": city, "offset": offset, "extensions": "all"}
        if types:
            params["types"] = types
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AMAP_BASE}/place/text", params=params)
            data = resp.json()
            if data.get("status") == "1":
                return data.get("pois", [])
            raise RuntimeError(f"高德 POI 搜索失败: {data.get('info', 'unknown')}")

    async def get_weather(self, city: str) -> dict:
        """天气预报查询 (extensions=all 获取多日预报)."""
        params = {"key": self.api_key, "city": city, "extensions": "all"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AMAP_BASE}/weather/weatherInfo", params=params)
            data = resp.json()
            if data.get("status") == "1":
                forecasts = data.get("forecasts", [])
                if forecasts:
                    return forecasts[0]
            raise RuntimeError(f"高德天气查询失败: {data.get('info', 'unknown')}")

    async def get_geocode(self, address: str, city: str = "") -> dict | None:
        """地理编码: 地址 → 经纬度."""
        params = {"key": self.api_key, "address": address, "city": city}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AMAP_BASE}/geocode/geo", params=params)
            data = resp.json()
            if data.get("status") == "1" and data.get("geocodes"):
                return data["geocodes"][0]
            return None

    async def get_driving_distance(self, origin: str, destination: str) -> dict | None:
        """驾车路线规划: origin/destination 格式 'lng,lat'."""
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
                return paths[0] if paths else None
            return None
