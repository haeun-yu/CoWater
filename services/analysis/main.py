"""
Analysis 서비스 진입점.

- Redis pub/sub 구독 (detect.*)
- Analysis Agent 초기화
- analyze.* 이벤트 발행
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from shared.events import Event, EventType
from config import settings
from anomaly_ai import AnalysisAnomalyAIAgent
from report_agent import AnalysisReportAgent

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_anomaly_ai_agent: AnalysisAnomalyAIAgent | None = None
_report_agent: AnalysisReportAgent | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Consumer loop
# ─────────────────────────────────────────────────────────────────────────────


async def _consume_detect_events(redis: aioredis.Redis) -> None:
    """detect.* 이벤트 구독 및 분석"""
    pubsub = redis.pubsub()
    pattern = "detect.*"
    await pubsub.psubscribe(pattern)
    logger.info("Analysis service: subscribed to %s", pattern)

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            data = json.loads(msg["data"])
            event = Event.from_json(json.dumps(data))

            # Detection 이벤트를 분석 Agent에게 전달
            if _anomaly_ai_agent and event.type == EventType.DETECT_ANOMALY:
                await _anomaly_ai_agent.on_detect_event(event)

        except Exception as e:
            logger.exception("Error processing detect event: %s", e)


async def _heartbeat_loop(redis: aioredis.Redis) -> None:
    """주기적으로 agent 상태 신호 송신"""
    while True:
        await asyncio.sleep(settings.heartbeat_interval_sec)

        if _anomaly_ai_agent:
            try:
                await _anomaly_ai_agent.send_heartbeat()
            except Exception as e:
                logger.error("Failed to send heartbeat: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _anomaly_ai_agent, _report_agent

    # Startup
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    _anomaly_ai_agent = AnalysisAnomalyAIAgent(
        redis=_redis,
        core_api_url=settings.core_api_url,
    )

    _report_agent = AnalysisReportAgent(
        redis=_redis,
        core_api_url=settings.core_api_url,
    )

    logger.info("Analysis service started")

    # 백그라운드 타스크 시작
    tasks = [
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

    logger.info("Analysis service stopped")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="CoWater Analysis Service", version="0.1.0", lifespan=lifespan)

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
        "agents": 2,  # anomaly-ai, report
        "dependencies": {
            "redis": "ok" if redis_ok else "error",
        },
    }


@app.post("/agents/report-agent/generate")
async def generate_report(request: dict):
    """보고서 생성"""
    if not _report_agent:
        raise HTTPException(503, "Report agent not available")

    alert_ids = request.get("alert_ids", [])
    report_type = request.get("report_type", "summary")

    if not alert_ids:
        raise HTTPException(400, "alert_ids is required")

    report = await _report_agent.generate_report(alert_ids, report_type)

    return {
        "alert_ids": alert_ids,
        "report_type": report_type,
        "report": report,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
