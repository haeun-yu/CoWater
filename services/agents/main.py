"""
Agent Runtime 진입점.

- Redis pub/sub 구독 (platform.report.*, alert.created.*)
- 등록된 Agent들에 이벤트 전달
- FastAPI로 Agent 토글/레벨 제어 API 제공
- AIS Timeout 주기 체크 (60초마다)
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai.anomaly_ai import AnomalyAIAgent
from ai.distress_agent import DistressAgent
from ai.report_agent import ReportAgent
from base import Agent, PlatformReport
from config import settings
from registry import AgentRegistry
from rule.anomaly_rule import AnomalyRuleAgent
from rule.cpa_agent import CPAAgent
from rule.zone_monitor import ZoneMonitorAgent

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

_registry = AgentRegistry()
_redis: aioredis.Redis | None = None


# ── 초기화 ──────────────────────────────────────────────────────────────────

def _setup_agents(redis: aioredis.Redis) -> None:
    agents: list[Agent] = [
        CPAAgent(redis),
        ZoneMonitorAgent(redis, settings.core_api_url),
        AnomalyRuleAgent(redis),
        AnomalyAIAgent(redis),
        DistressAgent(redis),
        ReportAgent(redis),
    ]
    for agent in agents:
        _registry.register(agent)


# ── Redis 컨슈머 ─────────────────────────────────────────────────────────────

async def _consume_platform_reports(redis: aioredis.Redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.psubscribe("platform.report.*")
    logger.info("Agent Runtime: subscribed to platform.report.*")

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue
        try:
            data = json.loads(msg["data"])
            report = PlatformReport.from_dict(data)
            for agent in _registry.enabled():
                await agent.on_platform_report(report)
        except Exception:
            logger.exception("Error dispatching platform report")


async def _consume_alerts(redis: aioredis.Redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.psubscribe("alert.created.*")
    logger.info("Agent Runtime: subscribed to alert.created.*")

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue
        try:
            alert = json.loads(msg["data"])
            for agent in _registry.enabled():
                await agent.on_alert(alert)
        except Exception:
            logger.exception("Error dispatching alert")


async def _ais_timeout_loop() -> None:
    """60초마다 AIS 타임아웃 체크."""
    while True:
        await asyncio.sleep(60)
        for agent in _registry.enabled():
            if isinstance(agent, AnomalyRuleAgent):
                await agent.check_ais_timeout()


async def _zone_reload_loop(redis: aioredis.Redis) -> None:
    """5분마다 Zone 목록 재로드."""
    for agent in _registry.all():
        if isinstance(agent, ZoneMonitorAgent):
            await agent.load_zones()
    while True:
        await asyncio.sleep(300)
        for agent in _registry.enabled():
            if isinstance(agent, ZoneMonitorAgent):
                await agent.load_zones()


# ── FastAPI ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    _setup_agents(_redis)

    tasks = [
        asyncio.create_task(_consume_platform_reports(_redis)),
        asyncio.create_task(_consume_alerts(_redis)),
        asyncio.create_task(_ais_timeout_loop()),
        asyncio.create_task(_zone_reload_loop(_redis)),
    ]
    logger.info("Agent Runtime started with %d agent(s)", len(_registry.all()))
    yield

    for t in tasks:
        t.cancel()
    await _redis.aclose()
    logger.info("Agent Runtime stopped")


app = FastAPI(title="CoWater Agent Runtime", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Agent 제어 API ────────────────────────────────────────────────────────────

@app.get("/agents")
async def list_agents():
    return [a.health() for a in _registry.all()]


@app.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = _registry.get(agent_id)
    if not agent:
        raise HTTPException(404)
    return agent.health()


@app.patch("/agents/{agent_id}/enable")
async def enable_agent(agent_id: str):
    if not _registry.enable(agent_id):
        raise HTTPException(404)
    return {"agent_id": agent_id, "enabled": True}


@app.patch("/agents/{agent_id}/disable")
async def disable_agent(agent_id: str):
    if not _registry.disable(agent_id):
        raise HTTPException(404)
    return {"agent_id": agent_id, "enabled": False}


class LevelBody(BaseModel):
    level: str


@app.patch("/agents/{agent_id}/level")
async def set_level(agent_id: str, body: LevelBody):
    if body.level not in ("L1", "L2", "L3"):
        raise HTTPException(400, "level must be L1, L2, or L3")
    if not _registry.set_level(agent_id, body.level):
        raise HTTPException(404)
    return {"agent_id": agent_id, "level": body.level}


@app.patch("/agents/{agent_id}/config")
async def set_config(agent_id: str, body: dict):
    if not _registry.set_config(agent_id, body):
        raise HTTPException(404)
    return {"agent_id": agent_id, "config": body}


@app.post("/agents/report-agent/generate/{incident_id}")
async def generate_report(incident_id: str):
    agent = _registry.get("report-agent")
    if not agent or not isinstance(agent, ReportAgent):
        raise HTTPException(404)
    report = await agent.generate_report(incident_id)
    if report is None:
        raise HTTPException(500, "Report generation failed")
    return {"incident_id": incident_id, "report": report}


@app.get("/health")
async def health():
    return {"status": "ok", "agents": len(_registry.all())}
