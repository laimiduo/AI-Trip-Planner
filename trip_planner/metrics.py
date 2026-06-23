"""Prometheus 指标 — 使用 prometheus_client 直连, 避免 starlette 版本冲突."""

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# === 计数器 ===
HTTP_REQUESTS_TOTAL = Counter("http_requests_total", "总请求数", ["method", "path", "status"])
LLM_CALLS_TOTAL = Counter("llm_calls_total", "LLM 调用次数", ["status"])
CACHE_HITS_TOTAL = Counter("cache_hits_total", "缓存命中次数", ["backend"])
CACHE_MISSES_TOTAL = Counter("cache_misses_total", "缓存未命中次数", ["backend"])

# === 直方图 ===
HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP 请求耗时 (秒)", ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)
LLM_GENERATION_DURATION = Histogram(
    "llm_generation_duration_seconds", "LLM 生成耗时 (秒)",
    buckets=(1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """采集 HTTP 请求指标."""

    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        start = time.monotonic()
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            status = 500
            raise
        finally:
            duration = time.monotonic() - start
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
            HTTP_REQUEST_DURATION.labels(method=method, path=path).observe(duration)


async def metrics_endpoint(request: Request) -> Response:
    """返回 Prometheus 格式指标."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
