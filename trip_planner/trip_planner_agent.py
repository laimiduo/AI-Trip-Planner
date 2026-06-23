import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
from hashlib import md5

from amap_client import AmapClient
from prompts import PLANNER_SYSTEM_PROMPT
from schemas import TripPlan, TripRequest

from my_llm import llm
from trip_planner.cache import cache_key, make_cache_backend
from trip_planner.config import get_settings


class MultiAgentTripPlanner:
    """旅行规划器 — 直连高德 API + 单次 LLM 结构化输出."""

    def __init__(self):
        self.llm = llm
        self.cache = make_cache_backend(get_settings().REDIS_URL, get_settings().ENABLE_CACHE)
        self.amap = AmapClient(cache=self.cache)

    async def initialize(self):
        """无需 MCP 初始化，保留以兼容旧调用方."""
        print("✅ 系统就绪 (直连高德 API 模式)")

    async def plan_trip(self, request: TripRequest) -> TripPlan:
        """多源数据采集 + 单次 LLM 调用生成计划."""

        # 检查 LLM 缓存
        cache_key_str = self._request_cache_key(request)
        cached = await self.cache.get(cache_key_str)
        if cached is not None:
            print("✅ LLM 缓存命中，直接返回")
            data = json.loads(cached)
            return TripPlan(**self._fill_defaults(data, request))

        print(f"\n{'='*60}")
        print("🚀 开始规划旅行...")
        print(f"目的地: {request.city} | {request.start_date} ~ {request.end_date} ({request.travel_days}天)")
        print(f"{'='*60}\n")

        # 并行采集数据 (0 次 LLM 调用)
        print("🔄 并行采集数据: 天气 / 景点 / 酒店...")
        weather_data, attraction_data, hotel_data = await asyncio.gather(
            self._collect_weather(request),
            self._collect_attractions(request),
            self._collect_hotels(request),
        )
        print(f"✅ 天气数据: {len(weather_data)} 天")
        print(f"✅ 景点数据: {len(attraction_data)} 个")
        print(f"✅ 酒店数据: {len(hotel_data)} 个\n")

        # 单次 LLM 调用生成计划
        print("📋 正在生成行程计划...")
        plan = await self._generate_plan(request, weather_data, attraction_data, hotel_data)

        # 写入缓存 (1h TTL)
        try:
            plan_json = plan.model_dump_json() if hasattr(plan, "model_dump_json") else json.dumps(plan)
            await self.cache.set(cache_key_str, plan_json, 3600)
        except Exception:
            pass

        print("✅ 旅行计划生成完成!\n")
        return plan

    def _request_cache_key(self, request: TripRequest) -> str:
        """基于请求内容生成缓存键."""
        raw = json.dumps(request.model_dump() if hasattr(request, "model_dump") else request.__dict__, sort_keys=True)
        return cache_key("llm:plan", md5(raw.encode()).hexdigest())

    async def _collect_weather(self, request: TripRequest) -> list[dict]:
        """从高德直接获取天气预报."""
        try:
            forecast = await self.amap.get_weather(request.city)
            return forecast.get("casts", [])
        except Exception as e:
            print(f"  天气查询失败: {e}")
            return []

    @staticmethod
    def _trim_poi(pois: list[dict], max_count: int = 6) -> list[dict]:
        """只保留 POI 的核心字段，减少传给 LLM 的 token 量."""
        kept = []
        for p in pois[:max_count]:
            kept.append({
                "name": p.get("name", ""),
                "address": p.get("address", ""),
                "type": p.get("type", ""),
                "location": p.get("location", ""),
                "rating": p.get("biz_ext", {}).get("rating", "") if isinstance(p.get("biz_ext"), dict) else "",
            })
        return kept

    async def _collect_attractions(self, request: TripRequest) -> list[dict]:
        """从高德 POI 搜索获取景点."""
        try:
            keywords = ", ".join(request.preferences) if request.preferences else "旅游景点"
            pois = await self.amap.search_poi(keywords, request.city, types="旅游景点")
            return self._trim_poi(pois, 6)
        except Exception as e:
            print(f"  景点搜索失败: {e}")
            return []

    async def _collect_hotels(self, request: TripRequest) -> list[dict]:
        """从高德 POI 搜索获取酒店."""
        try:
            pois = await self.amap.search_poi(f"{request.accommodation} 酒店", request.city, types="住宿服务")
            return self._trim_poi(pois, 4)
        except Exception as e:
            print(f"  酒店搜索失败: {e}")
            return []

    def _build_user_message(self, request: TripRequest, weather_data, attraction_data, hotel_data) -> str:
        """构建 LLM 用户消息."""
        def _dump(x):
            return json.dumps(x, ensure_ascii=False, indent=2)
        attractions_text = _dump(attraction_data) if attraction_data else "暂无景点数据"
        weather_text = _dump(weather_data) if weather_data else "暂无天气数据"
        hotels_text = _dump(hotel_data) if hotel_data else "暂无酒店数据"

        preferences = ", ".join(request.preferences) if request.preferences else "无"
        cuisine = ", ".join(request.cuisine_preferences) if request.cuisine_preferences else "无特殊偏好"

        budget_text = ""
        if request.budget_min or request.budget_max:
            budget_text = f"预算范围: {request.budget_min or '不限'} - {request.budget_max or '不限'} 元"

        extra_text = ""
        if request.free_text_input:
            extra_text = f"\n**额外要求:** {request.free_text_input}"

        return f"""请根据以下信息生成详细的{request.travel_days}天旅行计划:

**基本信息:**
城市: {request.city}
日期: {request.start_date} ~ {request.end_date} ({request.travel_days}天)
交通方式: {request.transportation}
住宿偏好: {request.accommodation}
偏好: {preferences}
人数: {request.traveler_count}, 出行类型: {request.traveler_type}
行程节奏: {request.pace}
饮食偏好: {cuisine}
{budget_text}

**景点数据 (来自高德地图):**
{attractions_text}

**天气数据 (来自高德地图):**
{weather_text}

**酒店数据 (来自高德地图):**
{hotels_text}{extra_text}"""

    async def _generate_plan(
        self,
        request: TripRequest,
        weather_data: list[dict],
        attraction_data: list[dict],
        hotel_data: list[dict],
    ) -> TripPlan:
        """单次 LLM 调用 (文本生成) → JSON 提取 → 默认值填充.

        DeepSeek-V4-Flash 不支持 with_structured_output, 直接走文本+解析路径.
        """
        user_message = self._build_user_message(request, weather_data, attraction_data, hotel_data)

        text = await self.llm.ainvoke([
            ("system", PLANNER_SYSTEM_PROMPT + "\n请直接输出 JSON，不要附加任何解释文字。"),
            ("user", user_message),
        ])
        text = text.content if hasattr(text, "content") else str(text)
        return self._parse_json_to_trip_plan(text, request)

    def _fill_defaults(self, data: dict, request: TripRequest) -> dict:
        """补充缺失的必需字段."""
        data.setdefault("city", request.city)
        data.setdefault("start_date", request.start_date)
        data.setdefault("end_date", request.end_date)
        data.setdefault("overall_suggestions", f"祝您在{request.city}旅途愉快！")
        # 处理 null 值
        if data.get("budget") is None:
            data["budget"] = {}
        if data.get("weather_info") is None:
            data["weather_info"] = []
        if data.get("days") is None:
            data["days"] = []
        data.setdefault("weather_info", [])
        data.setdefault("days", [])
        valid_days = []
        for i, day in enumerate(data.get("days", [])):
            if not isinstance(day, dict):
                continue
            day.setdefault("day_index", i)
            day.setdefault("date", "")
            day.setdefault("description", f"第{i+1}天")
            day.setdefault("transportation", request.transportation)
            day.setdefault("accommodation", request.accommodation)
            day.setdefault("meals", [])
            day.setdefault("attractions", [])
            day.setdefault("traffic_tips", [])
            day.setdefault("packing_suggestions", [])
            day.setdefault("local_events", [])
            for a in day.get("attractions", []):
                if not isinstance(a, dict):
                    continue
                a.setdefault("address", "")
                a.setdefault("visit_duration", 120)
                a.setdefault("description", "")
                a.setdefault("ticket_price", 0)
                if "location" not in a or not a["location"]:
                    a["location"] = {"longitude": 0, "latitude": 0}
            for m in day.get("meals", []):
                if not isinstance(m, dict):
                    continue
                if "name" not in m or not m["name"]:
                    m["name"] = m.get("recommend", m.get("restaurant", m.get("type", "用餐")))
                if "type" not in m or not m["type"]:
                    t = m.get("time", "")
                    if "早" in t or "breakfast" in t.lower():
                        m["type"] = "breakfast"
                    elif "午" in t or "lunch" in t.lower():
                        m["type"] = "lunch"
                    elif "晚" in t or "dinner" in t.lower():
                        m["type"] = "dinner"
                    else:
                        m["type"] = "meal"
                m.setdefault("description", "")
                m.setdefault("estimated_cost", 0)
            hotel = day.get("hotel")
            if hotel and isinstance(hotel, dict):
                hotel.setdefault("estimated_cost", 0)
                if "location" not in hotel or not hotel["location"]:
                    hotel["location"] = {"longitude": 0, "latitude": 0}
            valid_days.append(day)
        data["days"] = valid_days
        # 自动计算人均预算
        bp = data.get("budget_per_person")
        bd = data.get("budget")
        if bp is None and isinstance(bd, dict) and bd.get("total") and request.traveler_count:
            data["budget_per_person"] = bd["total"] // request.traveler_count
        return data

    def _parse_json_to_trip_plan(self, text: str, request: TripRequest) -> TripPlan:
        """从 LLM 输出文本中提取 JSON 并转换为 TripPlan."""
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            start = text.find('{')
            end = text.rfind('}')
            if start == -1 or end == -1:
                raise ValueError("未找到 JSON 数据")
            data = json.loads(text[start:end+1])
        data = self._fill_defaults(data, request)
        return TripPlan(**data)


_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体系统实例（单例模式）."""
    global _multi_agent_planner
    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()
    return _multi_agent_planner


async def main():
    """测试入口."""
    planner = MultiAgentTripPlanner()
    await planner.initialize()
    request = TripRequest(
        city="北京",
        start_date="2025-12-16",
        end_date="2025-12-18",
        travel_days=3,
        transportation="公共公交",
        accommodation="经济型酒店",
        preferences=["历史文化", "美食"],
        free_text_input="多安排博物馆，避免拥挤景点",
        traveler_count=2,
        traveler_type="couple",
        pace="moderate",
        cuisine_preferences=["北京烤鸭", "涮羊肉"],
    )
    try:
        trip_plan = await planner.plan_trip(request)
        print("\n✅ 生成的旅行计划：")
        print(trip_plan.model_dump_json(indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"规划失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
