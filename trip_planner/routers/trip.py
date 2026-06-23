"""旅行计划路由 (从 main.py 抽取)."""

import asyncio
import json
import time
import uuid
from typing import Optional

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from schemas import TripPlan, TripPlanResponse, TripRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from trip_planner_agent import get_trip_planner_agent

from trip_planner.cache import cache_key, make_cache_backend
from trip_planner.config import get_settings
from trip_planner.dependencies import get_db_session
from trip_planner.models import TravelPlan

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
            # 检查 LLM 缓存
            cache_key_str = planner._request_cache_key(request)
            cached = await planner.cache.get(cache_key_str)
            if cached is not None:
                msg = "Redis 缓存命中，直接返回..."
                yield {"event": "progress", "data": json.dumps({"step": 4, "total": 4, "message": msg})}
                data = planner._fill_defaults(json.loads(cached), request)
                plan = TripPlan(**data)
                yield {"event": "result", "data": plan.model_dump_json()}
                return

            yield {"event": "progress", "data": json.dumps({"step": 1, "total": 4, "message": "正在查询天气信息..."})}
            weather_task = planner._collect_weather(request)
            yield {"event": "progress", "data": json.dumps({"step": 2, "total": 4, "message": "正在搜索景点..."})}
            attraction_task = planner._collect_attractions(request)
            yield {"event": "progress", "data": json.dumps({"step": 3, "total": 4, "message": "正在搜索酒店..."})}
            hotel_task = planner._collect_hotels(request)
            weather_data, attraction_data, hotel_data = await asyncio.gather(weather_task, attraction_task, hotel_task)
            yield {"event": "progress", "data": json.dumps({"step": 4, "total": 4, "message": "正在生成行程计划..."})}
            plan = await planner._generate_plan(request, weather_data, attraction_data, hotel_data)
            # 写入 LLM 缓存 (1h TTL)
            try:
                plan_json = plan.model_dump_json()
                await planner.cache.set(cache_key_str, plan_json, 3600)
            except Exception:
                pass
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
                        ch = message["channel"]
                        channel = ch.decode() if isinstance(ch, bytes) else ch
                        d = message["data"]
                        data = d.decode() if isinstance(d, bytes) else d
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
        import asyncio

        from trip_planner.database import _async_session_maker, is_db_ready
        from trip_planner.models import TravelPlan
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


# ─── 历史记录 ────────────────────────────────────────────────


class PlanListItem(BaseModel):
    """历史列表条目 (摘要)."""
    id: str
    city: str
    start_date: str
    end_date: str
    travel_days: int
    created_at: str
    budget_total: int = 0
    traveler_count: int = 1


class PlanDetail(BaseModel):
    """单个计划详情."""
    id: str
    city: str
    start_date: str
    end_date: str
    travel_days: int
    created_at: str
    plan: Optional[TripPlan] = None


@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db_session)):
    """获取所有旅行计划列表 (按创建时间倒序)."""
    result = await db.execute(
        select(TravelPlan).order_by(TravelPlan.created_at.desc())
    )
    records = result.scalars().all()
    items = []
    for r in records:
        total = 0
        if r.plan_json and isinstance(r.plan_json, dict):
            budget = r.plan_json.get("budget") or {}
            total = budget.get("total", 0)
        items.append(PlanListItem(
            id=str(r.id),
            city=r.city,
            start_date=r.start_date,
            end_date=r.end_date,
            travel_days=r.travel_days,
            created_at=r.created_at.isoformat(),
            budget_total=total,
            traveler_count=r.traveler_count or 1,
        ))
    return {"success": True, "plans": items}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str, db: AsyncSession = Depends(get_db_session)):
    """获取单个旅行计划详情."""
    try:
        uid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "无效的 ID 格式")

    result = await db.execute(select(TravelPlan).where(TravelPlan.id == uid))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "计划不存在")

    plan = TripPlan(**record.plan_json) if record.plan_json else None
    return PlanDetail(
        id=str(record.id),
        city=record.city,
        start_date=record.start_date,
        end_date=record.end_date,
        travel_days=record.travel_days,
        created_at=record.created_at.isoformat(),
        plan=plan,
    )


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str, db: AsyncSession = Depends(get_db_session)):
    """删除旅行计划 (级联删除关联反馈)."""
    try:
        uid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(400, "无效的 ID 格式")

    result = await db.execute(select(TravelPlan).where(TravelPlan.id == uid))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "计划不存在")

    await db.delete(record)
    await db.commit()
    return {"success": True, "message": "已删除"}
