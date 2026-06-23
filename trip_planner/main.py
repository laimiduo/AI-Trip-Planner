"""FastAPI 应用入口 — 生命周期 + 路由注册."""

import os
import sys

# 确保能以 trip_planner.xxx 形式导入自身模块
_pkg_dir = os.path.dirname(__file__)
_parent_dir = os.path.dirname(_pkg_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from contextlib import asynccontextmanager  # noqa: E402

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from trip_planner.cache import NullCache, make_cache_backend  # noqa: E402
from trip_planner.config import get_settings  # noqa: E402
from trip_planner.metrics import PrometheusMiddleware, metrics_endpoint  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 初始化缓存 / 数据库 / Prometheus."""
    settings = get_settings()

    cache = make_cache_backend(settings.REDIS_URL, settings.ENABLE_CACHE)
    app.state.cache = cache
    print(f"  缓存后端: {'Redis' if not isinstance(cache, NullCache) else 'NullCache (降级)'}")

    if settings.DATABASE_URL and settings.ENABLE_DB:
        try:
            from trip_planner.database import create_tables, init_db
            await init_db(settings.DATABASE_URL)
            await create_tables()
            print("  数据库: 已连接")
        except Exception as e:
            print(f"  数据库连接失败 (跳过): {e}")
    else:
        print("  数据库: 未配置 (跳过)")

    yield

    from trip_planner.database import close_db
    await close_db()


app = FastAPI(title="AI旅行助手", version="2.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Prometheus ---
app.add_middleware(PrometheusMiddleware)
app.add_route("/metrics", metrics_endpoint, include_in_schema=False)
print("  Prometheus: /metrics 已注册")

# --- 路由 ---
from routers.feedback import router as feedback_router  # noqa: E402
from routers.trip import router as trip_router  # noqa: E402

app.include_router(trip_router)
app.include_router(feedback_router)


@app.get("/")
async def root():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


@app.get("/health")
async def health():
    """健康检查."""
    from trip_planner.database import is_db_ready
    return {
        "status": "ok",
        "version": "2.1",
        "cache": "enabled" if not isinstance(getattr(app.state, "cache", None), NullCache) else "disabled",
        "database": "connected" if is_db_ready() else "disabled",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
