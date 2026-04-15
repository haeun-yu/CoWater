"""
Response 서비스 진입점.

- Redis pub/sub 구독 (analyze.*)
- Response Agent 초기화
- Alert 생성 및 대응
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from shared.events import Event, EventType
from config import settings
from alert_creator import ResponseAlertCreatorAgent
from distress_agent import ResponseDistressAgent

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_alert_creator_agent: ResponseAlertCreatorAgent | None = None
_distress_agent: ResponseDistressAgent | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Consumer loop
# ─────────────────────────────────────────────────────────────────────────────


async def _consume_analyze_events(redis: aioredis.Redis) -> None:
    """analyze.* 이벤트 구독 및 대응"""
    pubsub = redis.pubsub()
    pattern = "analyze.*"
    await pubsub.psubscribe(pattern)
    logger.info("Response service: subscribed to %s", pattern)

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            data = json.loads(msg["data"])
            event = Event.from_json(json.dumps(data))

            # 분석 이벤트를 대응 Agent에게 전달
            if _alert_creator_agent:
                await _alert_creator_agent.on_analyze_event(event)
            if _distress_agent:
                await _distress_agent.on_analyze_event(event)

        except Exception as e:
            logger.exception("Error processing analyze event: %s", e)


async def _consume_detect_events(redis: aioredis.Redis) -> None:
    """detect.* 이벤트 중 response 단계가 직접 처리할 항목 구독"""
    pubsub = redis.pubsub()
    pattern = "detect.*"
    await pubsub.psubscribe(pattern)
    logger.info("Response service: subscribed to %s", pattern)

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            data = json.loads(msg["data"])
            event = Event.from_json(json.dumps(data))
            if _distress_agent:
                await _distress_agent.on_detect_event(event)
        except Exception as e:
            logger.exception("Error processing detect event: %s", e)


async def _heartbeat_loop(redis: aioredis.Redis) -> None:
    """주기적으로 agent 상태 신호 송신"""
    while True:
        await asyncio.sleep(settings.heartbeat_interval_sec)

        for agent in (_alert_creator_agent, _distress_agent):
            if agent is None:
                continue
            try:
                await agent.send_heartbeat()
            except Exception as e:
                logger.error("Failed to send heartbeat: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _alert_creator_agent, _distress_agent

    # Startup
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    _alert_creator_agent = ResponseAlertCreatorAgent(
        redis=_redis,
        core_api_url=settings.core_api_url,
    )
    _distress_agent = ResponseDistressAgent(
        redis=_redis,
        core_api_url=settings.core_api_url,
    )

    logger.info("Response service started")

    # 백그라운드 타스크 시작
    tasks = [
        asyncio.create_task(_consume_analyze_events(_redis), name="analyze-consumer"),
        asyncio.create_task(_consume_detect_events(_redis), name="detect-consumer"),
        asyncio.create_task(_heartbeat_loop(_redis), name="heartbeat-loop"),
    ]

    yield

    # Shutdown
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if _redis:
        await _redis.aclose()

    logger.info("Response service stopped")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="CoWater Response Service", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

Instrumentator().instrument(app).expose(app)


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """서비스 상태"""
    redis_ok = False
    if _redis:
        try:
            redis_ok = bool(await _redis.ping())
        except Exception:
            pass

    return {
        "status": "ok" if redis_ok else "degraded",
        "agents": 2,
        "dependencies": {
            "redis": "ok" if redis_ok else "error",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
