"""
Detection 서비스 진입점.

- Redis pub/sub 구독 (platform.report.*)
- Detection Agent 초기화
- Event 발행
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from shared.events import platform_report_pattern
from shared.schemas.device_stream import DeviceStreamMessage
from shared.schemas.report import PlatformReport
from config import settings
from cpa_agent import DetectionCPAAgent
from anomaly_agent import DetectionAnomalyAgent
from zone_agent import DetectionZoneAgent
from distress_agent import DetectionDistressAgent
from mine_agent import DetectionMineAgent

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────

_redis: aioredis.Redis | None = None
_agents: list = []


# ─────────────────────────────────────────────────────────────────────────────
# Consumer loop
# ─────────────────────────────────────────────────────────────────────────────


async def _consume_platform_reports(redis: aioredis.Redis) -> None:
    """platform.report.* 이벤트 구독 및 처리"""
    pubsub = redis.pubsub()
    pattern = platform_report_pattern()
    await pubsub.psubscribe(pattern)
    logger.info("Detection service: subscribed to %s", pattern)

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            data = json.loads(msg["data"])
            report = PlatformReport.from_dict(data)

            # 모든 Detection Agent에게 report 전달
            for agent in _agents:
                try:
                    await agent.on_platform_report(report)
                except Exception as e:
                    logger.exception("Agent %s error: %s", agent.agent_id, e)

        except Exception as e:
            logger.exception("Error processing platform report: %s", e)


async def _consume_sonar_streams(redis: aioredis.Redis) -> None:
    """sensor.sonar.* 스트림 구독 및 mine detection 처리."""
    pubsub = redis.pubsub()
    pattern = "sensor.sonar.*"
    await pubsub.psubscribe(pattern)
    logger.info("Detection service: subscribed to %s", pattern)

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue

        try:
            data = json.loads(msg["data"])
            stream_message = DeviceStreamMessage.from_dict(data)

            for agent in _agents:
                handler = getattr(agent, "on_device_stream", None)
                if handler is None:
                    continue
                try:
                    await handler(stream_message)
                except Exception as e:
                    logger.exception("Agent %s stream error: %s", agent.agent_id, e)

        except Exception as e:
            logger.exception("Error processing sonar stream: %s", e)


async def _heartbeat_loop(redis: aioredis.Redis) -> None:
    """주기적으로 agent 상태 신호 송신"""
    while True:
        await asyncio.sleep(settings.heartbeat_interval_sec)

        for agent in _agents:
            try:
                await agent.send_heartbeat()
            except Exception as e:
                logger.error("Failed to send heartbeat for %s: %s", agent.agent_id, e)


async def _ais_timeout_loop() -> None:
    """주기적으로 AIS timeout 기반 anomaly 탐지 수행"""
    while True:
        await asyncio.sleep(settings.ais_check_interval_sec)

        for agent in _agents:
            check_timeout = getattr(agent, "check_ais_timeout", None)
            if check_timeout is None:
                continue
            try:
                await check_timeout()
            except Exception as e:
                logger.error("Failed AIS timeout check for %s: %s", agent.agent_id, e)


async def _zone_reload_loop() -> None:
    """주기적으로 Zone 캐시를 reload"""
    while True:
        await asyncio.sleep(settings.zone_reload_interval_sec)

        for agent in _agents:
            load_zones = getattr(agent, "load_zones", None)
            if load_zones is None:
                continue
            try:
                await load_zones()
            except Exception as e:
                logger.error("Failed zone reload for %s: %s", agent.agent_id, e)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app lifecycle
# ─────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _agents

    # Startup
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    # Detection Agent 초기화
    _agents = [
        DetectionCPAAgent(
            redis=_redis,
            core_api_url=settings.core_api_url,
            warning_cpa_nm=settings.cpa_warning_nm,
            warning_tcpa_min=settings.cpa_warning_tcpa_min,
            critical_cpa_nm=settings.cpa_critical_nm,
            critical_tcpa_min=settings.cpa_critical_tcpa_min,
        ),
        DetectionAnomalyAgent(
            redis=_redis,
            core_api_url=settings.core_api_url,
        ),
        DetectionZoneAgent(
            redis=_redis,
            core_api_url=settings.core_api_url,
        ),
        DetectionDistressAgent(
            redis=_redis,
            core_api_url=settings.core_api_url,
        ),
        DetectionMineAgent(
            redis=_redis,
            core_api_url=settings.core_api_url,
            confidence_threshold=settings.mine_detection_confidence_threshold,
            emit_cooldown_sec=settings.mine_detection_emit_cooldown_sec,
        ),
    ]

    for agent in _agents:
        restore_state = getattr(agent, "restore_state", None)
        if restore_state is None:
            continue
        try:
            await restore_state()
        except Exception:
            logger.exception("Failed to restore state for %s", agent.agent_id)

    for agent in _agents:
        load_zones = getattr(agent, "load_zones", None)
        if load_zones is None:
            continue
        try:
            await load_zones()
        except Exception:
            logger.exception("Failed to preload zones for %s", agent.agent_id)

    logger.info("Detection service started with %d agent(s)", len(_agents))

    # 백그라운드 타스크 시작
    tasks = [
        asyncio.create_task(_consume_platform_reports(_redis), name="platform-consumer"),
        asyncio.create_task(_consume_sonar_streams(_redis), name="sonar-consumer"),
        asyncio.create_task(_heartbeat_loop(_redis), name="heartbeat-loop"),
        asyncio.create_task(_ais_timeout_loop(), name="ais-timeout-loop"),
        asyncio.create_task(_zone_reload_loop(), name="zone-reload-loop"),
    ]

    yield

    # Shutdown
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if _redis:
        await _redis.aclose()

    logger.info("Detection service stopped")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="CoWater Detection Service", version="0.1.0", lifespan=lifespan)

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
        "agents": len(_agents),
        "dependencies": {
            "redis": "ok" if redis_ok else "error",
        },
    }


@app.get("/agents")
async def list_agents():
    """등록된 Detection Agent 목록"""
    return [
        {
            "agent_id": agent.agent_id,
            "type": "detection",
            "config": getattr(agent, "config", {}),
        }
        for agent in _agents
    ]


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """특정 Agent 정보"""
    agent = next((a for a in _agents if a.agent_id == agent_id), None)
    if not agent:
        return {"error": "Agent not found"}, 404

    return {
        "agent_id": agent.agent_id,
        "type": "detection",
        "config": getattr(agent, "config", {}),
    }


@app.patch("/agents/{agent_id}/config")
async def set_agent_config(agent_id: str, config: dict):
    """Agent 설정 업데이트"""
    agent = next((a for a in _agents if a.agent_id == agent_id), None)
    if not agent:
        return {"error": "Agent not found"}, 404

    if not hasattr(agent, "config") or not isinstance(agent.config, dict):
        return {"error": "Agent config is not mutable"}, 400

    agent.config.update(config)
    logger.info("Agent %s config updated: %s", agent_id, config)

    return {
        "agent_id": agent_id,
        "config": agent.config,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
