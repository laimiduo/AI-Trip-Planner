# 🧳 AI Trip Planner

**Production-grade travel planning system** — DeepSeek-V4-Flash + Amap REST API + FastAPI + Redis/PostgreSQL.

> 输入目的地 + 日期, ~47s 生成「可落地」的详细旅行计划 (景点/酒店/天气/预算)

---

## Architecture

```
Nginx (反向代理/限流)
  └─ FastAPI (ASGI)
       ├─ Redis Cache (Amap POI/Weather + LLM plan)
       ├─ ARQ Worker (异步后台任务队列)
       ├─ PostgreSQL (持久化旅行计划 + 反馈)
       └─ Prometheus (指标采集)
```

## Tech Stack

| 层 | 技术 | 用途 |
|----|------|------|
| AI | DeepSeek-V4-Flash (OpenAI-compatible) | 行程生成, 一次 LLM 调用 |
| API | FastAPI + Pydantic v2 + SSE | REST + 流式进度推送 |
| Cache | Redis + NullCache 降级 | Amap POI 缓存 24h / 天气 30min / LLM 1h |
| Queue | ARQ (async-native) | 后台异步任务, PubSub 进度 |
| DB | PostgreSQL 16 + SQLAlchemy 2.0 async | 旅行计划 + 反馈 |
| Migration | Alembic | 数据库版本管理 |
| Metrics | Prometheus | 请求量/延迟/错误率/缓存命中率 |
| Proxy | Nginx | 限流 60r/m, SSE 反代, 内网隔离 |
| CI | GitHub Actions | lint + test + build |

## Quick Start

```bash
# 1. 环境
conda create -n trip python=3.11 -y && conda activate trip

# 2. 依赖
pip install -r requirements.txt -r requirements-dev.txt

# 3. 密钥
cp .env.example .env
# 编辑 .env, 至少填写:
#   DEEPSEEK_API_KEY=sk-xxx
#   AMAP_API_KEY=xxx

# 4. 启动 (单服务模式, 无需 Redis/DB)
uvicorn trip_planner.main:app --reload --host 0.0.0.0 --port 8000

# 5. 访问
#   首页 http://127.0.0.1:8000/
#   API  http://127.0.0.1:8000/docs
```

## Docker Compose (全栈)

```bash
cp .env.example .env
# 编辑 .env, 添加:
#   REDIS_URL=redis://redis:6379
#   DATABASE_URL=postgresql://trip:trip_pass@db:5432/trip_planner

docker compose up --build
```

访问 `http://localhost/` (通过 Nginx 入口, 限流保护).

## API Endpoints

| Method | Path | 说明 |
|--------|------|------|
| POST | `/api/v1/trip/plan` | 同步生成 (默认) |
| POST | `/api/v1/trip/plan/stream` | SSE 流式进度推送 |
| POST | `/api/v1/trip/plan/async` | 异步提交 (需 Redis + Worker) |
| GET | `/api/v1/trip/plan/async/{id}/status` | 查询异步任务状态 |
| GET | `/api/v1/trip/plan/async/{id}/stream` | SSE 异步进度订阅 |
| POST | `/api/v1/feedback` | 提交用户反馈 (需 DB) |
| GET | `/api/v1/feedback` | 查看反馈列表 |
| GET | `/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |

## Project Structure

```
├── trip_planner/
│   ├── main.py               # FastAPI 入口 + lifespan
│   ├── config.py             # pydantic-settings 配置
│   ├── cache.py              # CacheBackend / RedisCache / NullCache
│   ├── database.py           # SQLAlchemy async engine
│   ├── models.py             # TravelPlan / Feedback ORM
│   ├── metrics.py            # Prometheus 指标 + 中间件
│   ├── background.py         # ARQ 后台任务
│   ├── worker.py             # ARQ worker 入口
│   ├── dependencies.py       # FastAPI Depends 工厂
│   ├── schemas.py            # Pydantic 模型
│   ├── prompts.py            # 系统提示词
│   ├── trip_planner_agent.py # 多源采集 + LLM 生成
│   ├── amap_client.py        # 高德 REST 客户端 (缓存)
│   ├── routers/
│   │   ├── trip.py           # 旅行计划路由
│   │   └── feedback.py       # 用户反馈路由
│   └── index.html            # 前端单页
├── tests/
│   ├── test_schemas.py       # Schema 验证
│   ├── test_cache.py         # 缓存后端
│   └── test_api.py           # API 端点
├── alembic/                  # 数据库迁移
├── nginx/
│   ├── nginx.conf            # 反向代理 + 限流
│   └── Dockerfile
├── prometheus/
│   └── prometheus.yml
├── .github/workflows/ci.yml
├── docker-compose.yml        # 6 服务编排
├── Dockerfile                # 多阶段构建
└── requirements.txt
```

## Cache Strategy

| 数据 | TTL | Key 模式 |
|------|-----|----------|
| 天气 | 30min | `amap:weather:{city}` |
| POI | 24h | `amap:poi:{md5}` |
| 地理编码 | 7天 | `amap:geocode:{md5}` |
| 驾车路线 | 1h | `amap:driving:{origin}:{dest}` |
| LLM 计划 | 1h | `llm:plan:{md5}` |

Redis 不可用时自动降级为 NullCache, 功能完全不变.

## Performance

- **首次请求**: ~47s (Amap 数据采集 + 1 次 LLM 调用)
- **缓存命中**: ~5s (直接从 Redis 返回)
- **LLM 调用**: 从 ~7 次降至 1 次

## Key Design Decisions

1. **NullCache + 可选 DB**: 所有新组件可选, 零配置 standalone 模式
2. **直连 Amap REST**: 去掉 MCP/SSE 中间层, 减少延迟和失败点
3. **ARQ 优于 Celery**: async-native, 基于 Redis, 无需额外 broker
4. **反范式化 Schema**: travel_plans 表存完整输入 + 输出, 避免 join
5. **Prometheus 指标先行**: 后续开发基于数据做决策
