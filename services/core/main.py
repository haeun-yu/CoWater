import asyncio
import logging
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from db import AsyncSessionLocal
from api.alerts import router as alerts_router
from api.platforms import router as platforms_router
from api.ws import router as ws_router
from api.zones import router as zones_router
from redis_client import close_redis, get_redis
from services.alert_consumer import consume_alerts
from services.track_consumer import consume_platform_reports

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_RECONNECT_MAX_DELAY = 60.0  # 최대 재연결 대기 시간(초)


async def _run_with_reconnect(
    coro_factory: Callable[[aioredis.Redis], Coroutine[Any, Any, None]],
    name: str,
    redis: aioredis.Redis,
) -> None:
    """컨슈머 코루틴이 예외로 종료될 경우 지수 백오프로 재연결.

    CancelledError는 상위(lifespan)에서 명시적으로 취소할 때만 발생하므로 그대로 전파.
    Redis 연결 오류나 파싱 오류로 루프가 끊겨도 자동 복구된다.
    """
    delay = 1.0
    while True:
        try:
            await coro_factory(redis)
            # 정상 반환(루프 종료)은 기대하지 않지만, 발생하면 재시작
            logger.warning("%s returned unexpectedly, restarting", name)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s crashed — reconnecting in %.1fs", name, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, _RECONNECT_MAX_DELAY)
        else:
            delay = 1.0  # 정상 재시작 시 백오프 초기화


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = await get_redis()

    tasks = [
        asyncio.create_task(
            _run_with_reconnect(consume_platform_reports, "track-consumer", redis),
            name="track-consumer",
        ),
        asyncio.create_task(
            _run_with_reconnect(consume_alerts, "alert-consumer", redis),
            name="alert-consumer",
        ),
    ]
    logger.info("CoWater Core Backend started")

    yield

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await close_redis()
    logger.info("CoWater Core Backend stopped")


app = FastAPI(
    title="CoWater Core API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(platforms_router)
app.include_router(alerts_router)
app.include_router(zones_router)
app.include_router(ws_router)

Instrumentator().instrument(app).expose(app)


@app.get("/health")
async def health():
    redis_ok = False
    database_ok = False

    try:
        redis = await get_redis()
        redis_ok = bool(await redis.ping())
    except Exception:
        logger.exception("Core health check: Redis ping failed")

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
            database_ok = True
    except Exception:
        logger.exception("Core health check: database query failed")

    return {
        "status": "ok" if redis_ok and database_ok else "degraded",
        "dependencies": {
            "redis": "ok" if redis_ok else "error",
            "database": "ok" if database_ok else "error",
        },
    }
