"""Report 서비스 진입점.

- Redis pub/sub 구독 (respond.*)
- Report Agent 초기화
- report.* 이벤트 발행 + DB 저장
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from shared.events import Event
from config import settings
from report_agent import AIReportAgent

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_report_agent: AIReportAgent | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Consumer loop
# ─────────────────────────────────────────────────────────────────────────────


async def _consume_respond_events(redis: aioredis.Redis) -> None:
    """respond.* 이벤트 구독 및 보고서 생성"""
    pubsub = redis.pubsub()
    pattern = "respond.*"
    await pubsub.psubscribe(pattern)
    logger.info("Report service: subscribed to %s", pattern)

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            data = json.loads(msg["data"])
            event = Event.from_json(json.dumps(data))
            if _report_agent:
                await _report_agent.on_respond_event(event)

        except Exception as e:
            logger.exception("Error processing respond event: %s", e)


async def _heartbeat_loop(redis: aioredis.Redis) -> None:
    """주기적으로 agent 상태 신호 송신"""
    while True:
        await asyncio.sleep(settings.heartbeat_interval_sec)

        if _report_agent:
            try:
                await _report_agent.send_heartbeat()
            except Exception as e:
                logger.error("Failed to send heartbeat: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _report_agent

    # Startup
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    _report_agent = AIReportAgent(redis=_redis)

    logger.info("Report service started")

    # 백그라운드 타스크 시작
    tasks = [
        asyncio.create_task(_consume_respond_events(_redis), name="respond-consumer"),
        asyncio.create_task(_heartbeat_loop(_redis), name="heartbeat-loop"),
    ]

    yield

    # Shutdown
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if _redis:
        await _redis.aclose()

    logger.info("Report service stopped")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="CoWater Report Service", version="0.1.0", lifespan=lifespan)

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
        "agents": 1,  # report-agent
        "dependencies": {
            "redis": "ok" if redis_ok else "error",
        },
    }


@app.post("/agents/report-agent/generate/{alert_id}")
async def generate_report(alert_id: str):
    if _report_agent is None:
        raise HTTPException(503, "Report agent unavailable")

    content = await _report_agent.generate_report(alert_id)
    if content is None:
        raise HTTPException(404, "Alert not found or report generation failed")
    return {"alert_id": alert_id, "report": content}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
