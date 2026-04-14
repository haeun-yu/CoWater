"""
Learning 서비스 진입점.

- Redis pub/sub 구독 (system.alert_acknowledge)
- Learning Agent 초기화
- 거짓 경보율 추적 및 규칙 조정 제안
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
from learning_agent import LearningAgent

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_learning_agent: LearningAgent | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Consumer loop
# ─────────────────────────────────────────────────────────────────────────────


async def _consume_feedback_events(redis: aioredis.Redis) -> None:
    """사용자 피드백 이벤트 구독"""
    pubsub = redis.pubsub()
    pattern = "system.ack.*"
    await pubsub.psubscribe(pattern)
    logger.info("Learning service: subscribed to %s", pattern)

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            data = json.loads(msg["data"])
            event = Event.from_json(json.dumps(data))

            # 피드백 이벤트를 Learning Agent에게 전달
            if _learning_agent:
                await _learning_agent.on_alert_feedback(event)

                # 피드백 통계 추적
                agent_id = event.payload.get("generated_by")
                feedback = event.payload.get("feedback")
                if agent_id and feedback:
                    await _learning_agent.track_feedback(agent_id, feedback)

        except Exception as e:
            logger.exception("Error processing feedback event: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _learning_agent

    # Startup
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    _learning_agent = LearningAgent(
        redis=_redis,
        core_api_url=settings.core_api_url,
    )

    logger.info("Learning service started")

    # 백그라운드 타스크 시작
    tasks = [
        asyncio.create_task(_consume_feedback_events(_redis), name="feedback-consumer"),
    ]

    yield

    # Shutdown
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if _redis:
        await _redis.aclose()

    logger.info("Learning service stopped")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="CoWater Learning Service", version="0.1.0", lifespan=lifespan)

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
        "dependencies": {
            "redis": "ok" if redis_ok else "error",
        },
    }


@app.get("/agents/{agent_id}/fp-rate")
async def get_fp_rate(agent_id: str):
    """Agent의 거짓 경보율 조회"""
    if not _learning_agent:
        return {"error": "Learning agent not available"}, 503

    fp_rate = await _learning_agent._calculate_fp_rate(agent_id)

    return {
        "agent_id": agent_id,
        "fp_rate": fp_rate,
        "percentage": f"{fp_rate*100:.1f}%",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
