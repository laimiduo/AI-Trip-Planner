"""Pytest fixtures — 测试配置."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "trip_planner"))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from trip_planner.cache import NullCache
from trip_planner.main import app


@pytest.fixture(scope="function")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    """FastAPI TestClient (async)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        app.state.cache = NullCache()
        yield ac


@pytest.fixture
def sample_request():
    """标准测试请求."""
    return {
        "city": "北京",
        "start_date": "2025-12-16",
        "end_date": "2025-12-18",
        "travel_days": 3,
        "transportation": "公共公交",
        "accommodation": "经济型酒店",
        "preferences": ["历史文化", "美食"],
        "traveler_count": 2,
        "traveler_type": "couple",
        "pace": "moderate",
        "cuisine_preferences": ["北京烤鸭"],
    }
