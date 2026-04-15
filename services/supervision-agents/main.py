"""
Supervision 서비스 진입점.

- 모든 Agent의 heartbeat 모니터링
- 장애 감지 및 알림
- 사용자 명령 추적 (user.* 이벤트)
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from config import settings
from supervisor import Supervisor

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_supervisor: Supervisor | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Monitoring loop
# ─────────────────────────────────────────────────────────────────────────────


async def _health_check_loop(supervisor: Supervisor) -> None:
    """주기적으로 모든 Agent 상태 확인"""
    while True:
        await asyncio.sleep(settings.health_check_interval_sec)

        health_status = await supervisor.check_health()

        # 장애 있는 Agent 찾기
        unhealthy = [aid for aid, status in health_status.items() if status != "healthy"]

        if unhealthy:
            logger.warning("Unhealthy agents: %s", unhealthy)
            await supervisor.emit_system_alert(
                alert_type="agent_health",
                message=f"{len(unhealthy)}개 Agent가 응답하지 않음",
                details={"unhealthy_agents": unhealthy},
            )


async def _consume_user_events(redis: aioredis.Redis) -> None:
    """user.* 이벤트 구독 (사용자 명령 추적)"""
    pubsub = redis.pubsub()
    pattern = "user.*"
    await pubsub.psubscribe(pattern)
    logger.info("Supervision service: subscribed to %s", pattern)

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            data = json.loads(msg["data"])
            user_id = data.get("user_id", "unknown")
            event_type = data.get("type", "unknown")

            logger.info("User activity: %s by %s", event_type, user_id)

            # 사용자 활동 기록 (선택적)
            # 예: 사용자가 명령을 실행했거나 피드백을 제출했을 때

        except Exception as e:
            logger.exception("Error processing user event: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _supervisor

    # Startup
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    _supervisor = Supervisor(_redis)

    logger.info("Supervision service started")

    # 백그라운드 타스크 시작
    tasks = [
        asyncio.create_task(_supervisor.start_monitoring(), name="heartbeat-monitor"),
        asyncio.create_task(_health_check_loop(_supervisor), name="health-check"),
        asyncio.create_task(_consume_user_events(_redis), name="user-consumer"),
    ]

    yield

    # Shutdown
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if _redis:
        await _redis.aclose()

    logger.info("Supervision service stopped")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="CoWater Supervision Service", version="0.1.0", lifespan=lifespan)

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


@app.get("/agents")
async def list_agents_health():
    """모든 Agent 상태 조회"""
    if not _supervisor:
        return {"error": "Supervisor not ready"}, 503

    health_status = await _supervisor.check_health()
    return {
        "timestamp": asyncio.get_event_loop().time(),
        "agents": health_status,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
