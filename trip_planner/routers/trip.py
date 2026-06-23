"""旅行计划路由 (从 main.py 抽取)."""

import asyncio
import json
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from arq import create_pool

from schemas import TripRequest, TripPlanResponse
from trip_planner_agent import get_trip_planner_agent
from trip_planner.cache import make_cache_backend, NullCache, cache_key
from trip_planner.config import get_settings
from trip_planner.background import BACKGROUND_TASKS

router = APIRouter(prefix="/api/v1/trip", tags=["trip"])
planner = get_trip_planner_agent()


class TaskSubmitResponse(BaseModel):
    success: bool
    task_id: str
    status_url: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # pending / processing / completed / failed
    progress: Optional[dict] = None
    result: Optional[dict] = None
    error: Optional[str] = None


@router.post("/plan", response_model=TripPlanResponse)
async def plan_trip(request: TripRequest):
    """非流式接口."""
    start = time.monotonic()
    try:
        await planner.initialize()
        plan = await planner.plan_trip(request)
        duration_ms = int((time.monotonic() - start) * 1000)
        _try_persist(request, plan, duration_ms)
        return TripPlanResponse(success=True, message="规划成功", data=plan)
    except Exception as e:
        return TripPlanResponse(success=False, message=str(e))


@router.post("/plan/stream")
async def plan_trip_stream(request: TripRequest):
    """SSE 流式接口."""
    async def event_generator():
        start = time.monotonic()
        try:
            yield {"event": "progress", "data": json.dumps({"step": 1, "total": 4, "message": "正在查询天气信息..."})}
            weather_task = planner._collect_weather(request)
            yield {"event": "progress", "data": json.dumps({"step": 2, "total": 4, "message": "正在搜索景点..."})}
            attraction_task = planner._collect_attractions(request)
            yield {"event": "progress", "data": json.dumps({"step": 3, "total": 4, "message": "正在搜索酒店..."})}
            hotel_task = planner._collect_hotels(request)
            weather_data, attraction_data, hotel_data = await asyncio.gather(weather_task, attraction_task, hotel_task)
            yield {"event": "progress", "data": json.dumps({"step": 4, "total": 4, "message": "正在生成行程计划..."})}
            plan = await planner._generate_plan(request, weather_data, attraction_data, hotel_data)
            duration_ms = int((time.monotonic() - start) * 1000)
            _try_persist(request, plan, duration_ms)
            yield {"event": "result", "data": plan.model_dump_json()}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
    return EventSourceResponse(event_generator())


@router.post("/plan/async", response_model=TaskSubmitResponse)
async def plan_trip_async(request: TripRequest):
    """异步提交任务: 立即返回 task_id, ARQ Worker 后台处理."""
    settings = get_settings()
    redis_url = settings.REDIS_URL
    if not redis_url:
        raise HTTPException(400, "Redis 未配置, 无法使用异步任务")

    task_id = str(uuid.uuid4())
    try:
        pool = await create_pool(redis_url)
        await pool.enqueue_job("generate_plan_task", request.model_dump(), _job_id=task_id)
    except Exception as e:
        raise HTTPException(500, f"提交任务失败: {e}")

    return TaskSubmitResponse(
        success=True,
        task_id=task_id,
        status_url=f"/api/v1/trip/plan/async/{task_id}/status",
    )


@router.get("/plan/async/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """查询异步任务状态."""
    settings = get_settings()
    cache = make_cache_backend(settings.REDIS_URL, settings.ENABLE_CACHE)

    result_data = await cache.get(cache_key("task", task_id, "result"))
    if result_data:
        parsed = json.loads(result_data)
        return TaskStatusResponse(
            task_id=task_id,
            status=parsed.get("status", "completed"),
            result=parsed.get("result"),
            error=parsed.get("error"),
        )

    progress_data = await cache.get(cache_key("task", task_id, "status"))
    if progress_data:
        parsed = json.loads(progress_data)
        return TaskStatusResponse(
            task_id=task_id,
            status="processing",
            progress=parsed,
        )

    return TaskStatusResponse(task_id=task_id, status="pending")


@router.get("/plan/async/{task_id}/stream")
async def stream_task_progress(task_id: str):
    """SSE 流式推送异步任务进度."""
    settings = get_settings()
    redis_url = settings.REDIS_URL
    cache = make_cache_backend(redis_url, settings.ENABLE_CACHE)

    async def event_generator():
        import redis.asyncio as aioredis

        pubsub = None
        try:
            if redis_url:
                r = aioredis.from_url(redis_url, decode_responses=True)
                pubsub = r.pubsub()
                await pubsub.subscribe(f"task:{task_id}:progress", f"task:{task_id}:result")

            # 先查缓存 (防止错过已结束的任务)
            result_data = await cache.get(cache_key("task", task_id, "result"))
            if result_data:
                yield {"event": "result", "data": result_data}
                return

            if pubsub:
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        channel = message["channel"].decode() if isinstance(message["channel"], bytes) else message["channel"]
                        data = message["data"].decode() if isinstance(message["data"], bytes) else message["data"]
                        if "result" in channel:
                            yield {"event": "result", "data": data}
                            return
                        else:
                            yield {"event": "progress", "data": data}
            else:
                yield {"event": "error", "data": json.dumps({"message": "Redis 不可用"})}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}
        finally:
            if pubsub:
                await pubsub.unsubscribe()
                await pubsub.connection.disconnect()

    return EventSourceResponse(event_generator())


def _try_persist(request: TripRequest, plan, duration_ms: int) -> None:
    """后台尝试保存到数据库 (异步 fire-and-forget)."""
    try:
        from trip_planner.database import is_db_ready, _async_session_maker
        from trip_planner.models import TravelPlan
        import asyncio
        if not is_db_ready():
            return

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
            plan_json=plan.model_dump() if hasattr(plan, "model_dump") else plan,
            model_name="deepseek-v4-flash",
            generation_duration_ms=duration_ms,
            status="completed",
        )
        # 在运行中的事件循环中创建任务
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_save_record(session, record))
        else:
            loop.run_until_complete(_save_record(session, record))
    except Exception as e:
        print(f"  持久化失败 (非致命): {e}")


async def _save_record(session, record):
    async with session:
        session.add(record)
        await session.commit()
