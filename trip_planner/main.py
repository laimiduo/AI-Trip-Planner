import asyncio
import json
import os
import sys

# 确保能导入同目录下的模块 (schemas, trip_planner_agent, amap_client 等)
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from schemas import TripRequest, TripPlanResponse
from trip_planner_agent import get_trip_planner_agent

app = FastAPI(title="AI旅行助手", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

planner = get_trip_planner_agent()


@app.post("/api/v1/trip/plan", response_model=TripPlanResponse)
async def plan_trip(request: TripRequest):
    """非流式接口（兼容旧调用方）."""
    try:
        await planner.initialize()
        plan = await planner.plan_trip(request)
        return TripPlanResponse(success=True, message="规划成功", data=plan)
    except Exception as e:
        return TripPlanResponse(success=False, message=str(e))


@app.post("/api/v1/trip/plan/stream")
async def plan_trip_stream(request: TripRequest):
    """SSE 流式接口：分步推送进度，最后推送完整结果."""

    async def event_generator():
        try:
            yield {"event": "progress", "data": json.dumps({"step": 1, "total": 4, "message": "正在查询天气信息..."})}
            weather_task = planner._collect_weather(request)

            yield {"event": "progress", "data": json.dumps({"step": 2, "total": 4, "message": "正在搜索景点..."})}
            attraction_task = planner._collect_attractions(request)

            yield {"event": "progress", "data": json.dumps({"step": 3, "total": 4, "message": "正在搜索酒店..."})}
            hotel_task = planner._collect_hotels(request)

            # 等待所有数据采集任务完成
            weather_data, attraction_data, hotel_data = await asyncio.gather(
                weather_task, attraction_task, hotel_task
            )

            yield {"event": "progress", "data": json.dumps({"step": 4, "total": 4, "message": "正在生成行程计划..."})}

            plan = await planner._generate_plan(request, weather_data, attraction_data, hotel_data)

            yield {"event": "result", "data": plan.model_dump_json()}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"message": str(e)})}

    return EventSourceResponse(event_generator())


@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
