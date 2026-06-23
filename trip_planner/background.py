"""ARQ 后台任务函数 — 异步生成旅行计划."""

import json
import time
import uuid
from typing import Optional

from trip_planner.cache import make_cache_backend, cache_key
from trip_planner.config import get_settings


async def generate_plan_task(ctx, request_data: dict) -> dict:
    """ARQ 后台任务: 采集数据 → LLM 生成 → 保存结果.

    由 ARQ worker 调用, ctx['redis'] 为 ARQ 传入的 redis 连接.
    """
    from schemas import TripRequest
    from trip_planner_agent import MultiAgentTripPlanner

    task_id = ctx.get("job_id", str(uuid.uuid4()))
    task_redis = ctx.get("redis")
    settings = get_settings()
    cache = make_cache_backend(settings.REDIS_URL, settings.ENABLE_CACHE)

    # 用于 PubSub 进度推送的辅助函数
    async def publish_progress(step: int, total: int, message: str):
        payload = json.dumps({"step": step, "total": total, "message": message, "task_id": task_id})
        if task_redis:
            await task_redis.publish(f"task:{task_id}:progress", payload)
        # 同时更新 task status 缓存
        await cache.set(cache_key("task", task_id, "status"), payload, 3600)

    async def publish_result(result_data: dict):
        payload = json.dumps({"task_id": task_id, "status": "completed", "result": result_data})
        if task_redis:
            await task_redis.publish(f"task:{task_id}:result", payload)
        # 缓存最终结果 1h
        await cache.set(cache_key("task", task_id, "result"), payload, 3600)

    async def publish_error(error: str):
        payload = json.dumps({"task_id": task_id, "status": "failed", "error": error})
        if task_redis:
            await task_redis.publish(f"task:{task_id}:result", payload)
        await cache.set(cache_key("task", task_id, "result"), payload, 3600)

    try:
        request = TripRequest(**request_data)
        planner = MultiAgentTripPlanner()

        await publish_progress(1, 5, "正在查询天气信息...")
        weather_data = await planner._collect_weather(request)

        await publish_progress(2, 5, "正在搜索景点...")
        attraction_data = await planner._collect_attractions(request)

        await publish_progress(3, 5, "正在搜索酒店...")
        hotel_data = await planner._collect_hotels(request)

        await publish_progress(4, 5, "正在生成行程计划...")
        start = time.monotonic()
        plan = await planner._generate_plan(request, weather_data, attraction_data, hotel_data)
        duration_ms = int((time.monotonic() - start) * 1000)

        result = plan.model_dump() if hasattr(plan, "model_dump") else plan

        # 尝试持久化到数据库
        try:
            from trip_planner.database import init_db, is_db_ready
            from trip_planner.models import TravelPlan
            if not is_db_ready() and settings.DATABASE_URL:
                await init_db(settings.DATABASE_URL)
            if is_db_ready():
                from trip_planner.database import _async_session_maker
                session = _async_session_maker()
                record = TravelPlan(
                    city=request.city,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    travel_days=request.travel_days,
                    transportation=request.transportation,
                    accommodation=request.accommodation,
                    preferences=request.preferences,
                    traveler_count=request.traveler_count,
                    traveler_type=request.traveler_type,
                    pace=request.pace,
                    cuisine_preferences=request.cuisine_preferences,
                    budget_min=request.budget_min,
                    budget_max=request.budget_max,
                    free_text_input=request.free_text_input,
                    plan_json=result,
                    model_name="deepseek-v4-flash",
                    generation_duration_ms=duration_ms,
                    status="completed",
                    task_id=task_id,
                )
                async with session:
                    session.add(record)
                    await session.commit()
        except Exception as e:
            print(f"  ARQ 持久化失败 (非致命): {e}")

        await publish_progress(5, 5, "旅行计划生成完成!")
        await publish_result(result)
        return result

    except Exception as e:
        await publish_error(str(e))
        raise


# ARQ 函数注册表 — Worker 通过此 dict 发现任务
BACKGROUND_TASKS: dict = {
    "generate_plan_task": generate_plan_task,
}
