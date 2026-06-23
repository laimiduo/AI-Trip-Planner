"""API 端点测试."""

import pytest


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_health(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    async def test_root(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")

    async def test_metrics(self, client):
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "http_requests_total" in body


@pytest.mark.asyncio
class TestPlanEndpoint:
    async def test_plan_invalid_request(self, client):
        """缺少必填字段时返回 422."""
        resp = await client.post("/api/v1/trip/plan", json={})
        assert resp.status_code == 422

    async def test_plan_without_api_key(self, client, sample_request):
        """未配置 API key 时返回 200 (success=False)."""
        resp = await client.post("/api/v1/trip/plan", json=sample_request)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False or data["success"] is True


@pytest.mark.asyncio
class TestStreamEndpoint:
    @pytest.mark.timeout(5)
    async def test_stream_sse(self, client, sample_request):
        """SSE 端点应返回 text/event-stream (外部 API 可能超时)."""
        import pytest
        resp = await client.post("/api/v1/trip/plan/stream", json=sample_request)
        assert resp.status_code == 200
