"""ARQ Worker 入口 — 单独进程运行."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trip_planner"))

from arq import create_pool
from arq.worker import Worker

from trip_planner.background import BACKGROUND_TASKS
from trip_planner.config import get_settings


async def startup(ctx):
    print("  ARQ Worker 启动完成")


async def shutdown(ctx):
    print("  ARQ Worker 关闭")


async def create_worker() -> Worker:
    settings = get_settings()
    redis_url = settings.REDIS_URL or "redis://localhost:6379"

    redis_pool = await create_pool(redis_url)

    worker = Worker(
        redis_pool=redis_pool,
        functions=BACKGROUND_TASKS,
        on_startup=startup,
        on_shutdown=shutdown,
        poll_delay=0.5,
        max_jobs=4,
    )
    return worker


if __name__ == "__main__":
    import asyncio

    async def main():
        worker = await create_worker()
        print(f"  ARQ Worker 运行中 (Redis: {get_settings().REDIS_URL or 'redis://localhost:6379'})")
        await worker.run()

    asyncio.run(main())
