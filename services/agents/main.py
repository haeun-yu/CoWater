"""
Agent Runtime 진입점.

- Redis pub/sub 구독 (platform.report.*, alert.created.*)
- 등록된 Agent들에 이벤트 전달
- FastAPI로 Agent 토글/레벨 제어 API 제공
- AIS Timeout 주기 체크 (20초마다)
- AI 에이전트 태스크 추적 + 타임아웃 + 우아한 종료
- 컨슈머 크래시 시 지수 백오프 자동 재연결
"""

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

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

# AI 에이전트 백그라운드 태스크 추적 집합
_pending_ai_tasks: set[asyncio.Task] = set()

# AI 에이전트 단일 호출 최대 허용 시간 (초)
_AI_TASK_TIMEOUT = 120.0

# 컨슈머 재연결 최대 대기 시간 (초)
_RECONNECT_MAX_DELAY = 60.0

# 종료 시 진행 중인 AI 태스크 drain 대기 시간 (초)
_SHUTDOWN_DRAIN_TIMEOUT = 15.0


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


# ── AI 태스크 헬퍼 ──────────────────────────────────────────────────────────

def _track_task(coro, *, name: str) -> asyncio.Task:
    """태스크를 생성하고 _pending_ai_tasks에 등록. 완료 시 자동 제거."""
    task = asyncio.create_task(coro, name=name)
    _pending_ai_tasks.add(task)
    task.add_done_callback(_pending_ai_tasks.discard)
    return task


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
            await _dispatch_report(report)
        except Exception:
            logger.exception("Error dispatching platform report")


async def _dispatch_report(report: PlatformReport) -> None:
    """
    Rule Agent: 순차 await (빠름, 이벤트 루프 차단 없음)
    AI Agent:   백그라운드 태스크로 실행 (Claude API 호출이 다음 보고 처리를 블로킹하지 않음)
    """
    rule_agents = [a for a in _registry.enabled() if a.agent_type == "rule"]
    ai_agents   = [a for a in _registry.enabled() if a.agent_type == "ai"]

    # Rule Agent — 직렬 처리 (순서 보장, 빠름)
    for agent in rule_agents:
        try:
            await agent.on_platform_report(report)
        except Exception:
            logger.exception("Rule agent error: %s", agent.agent_id)

    # AI Agent — 각각 독립 태스크로 실행 (블로킹 없음), 추적 집합에 등록
    for agent in ai_agents:
        _track_task(
            _safe_ai_dispatch(agent, report),
            name=f"ai-report-{agent.agent_id}",
        )


async def _safe_ai_dispatch(agent: Agent, report: PlatformReport) -> None:
    try:
        async with asyncio.timeout(_AI_TASK_TIMEOUT):
            await agent.on_platform_report(report)
    except TimeoutError:
        msg = f"AI dispatch timeout after {_AI_TASK_TIMEOUT}s"
        logger.warning("AI agent timed out: %s", agent.agent_id)
        agent._record_error(msg)
    except Exception as exc:
        logger.exception("AI agent error: %s", agent.agent_id)
        agent._record_error(str(exc))


async def _consume_alerts(redis: aioredis.Redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.psubscribe("alert.created.*")
    logger.info("Agent Runtime: subscribed to alert.created.*")

    async for msg in pubsub.listen():
        if msg["type"] != "pmessage":
            continue
        try:
            alert = json.loads(msg["data"])
            await _dispatch_alert(alert)
        except Exception:
            logger.exception("Error dispatching alert")


async def _dispatch_alert(alert: dict) -> None:
    rule_agents = [a for a in _registry.enabled() if a.agent_type == "rule"]
    ai_agents   = [a for a in _registry.enabled() if a.agent_type == "ai"]

    for agent in rule_agents:
        try:
            await agent.on_alert(alert)
        except Exception:
            logger.exception("Rule agent on_alert error: %s", agent.agent_id)

    for agent in ai_agents:
        _track_task(
            _safe_ai_alert(agent, alert),
            name=f"ai-alert-{agent.agent_id}",
        )


async def _safe_ai_alert(agent: Agent, alert: dict) -> None:
    try:
        async with asyncio.timeout(_AI_TASK_TIMEOUT):
            await agent.on_alert(alert)
    except TimeoutError:
        msg = f"AI on_alert timeout after {_AI_TASK_TIMEOUT}s"
        logger.warning("AI agent on_alert timed out: %s", agent.agent_id)
        agent._record_error(msg)
    except Exception as exc:
        logger.exception("AI agent on_alert error: %s", agent.agent_id)
        agent._record_error(str(exc))


async def _ais_timeout_loop() -> None:
    """20초마다 AIS 타임아웃 체크 (빠른 탐지)."""
    while True:
        await asyncio.sleep(20)
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


async def _run_with_reconnect(
    coro_factory: Callable[[aioredis.Redis], Coroutine[Any, Any, None]],
    name: str,
    redis: aioredis.Redis,
) -> None:
    """컨슈머가 예외로 종료될 경우 지수 백오프로 자동 재연결."""
    delay = 1.0
    while True:
        try:
            await coro_factory(redis)
            logger.warning("%s returned unexpectedly, restarting", name)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("%s crashed — reconnecting in %.1fs", name, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, _RECONNECT_MAX_DELAY)
        else:
            delay = 1.0


# ── FastAPI ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    _setup_agents(_redis)

    tasks = [
        asyncio.create_task(
            _run_with_reconnect(_consume_platform_reports, "platform-consumer", _redis),
            name="platform-consumer",
        ),
        asyncio.create_task(
            _run_with_reconnect(_consume_alerts, "alert-consumer", _redis),
            name="alert-consumer",
        ),
        asyncio.create_task(_ais_timeout_loop(), name="ais-timeout"),
        asyncio.create_task(_zone_reload_loop(_redis), name="zone-reload"),
    ]
    logger.info("Agent Runtime started with %d agent(s)", len(_registry.all()))
    yield

    # 메인 루프 태스크 취소
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # 진행 중인 AI 태스크 drain (최대 _SHUTDOWN_DRAIN_TIMEOUT초)
    if _pending_ai_tasks:
        logger.info("Waiting for %d pending AI task(s) to finish...", len(_pending_ai_tasks))
        done, pending = await asyncio.wait(
            _pending_ai_tasks, timeout=_SHUTDOWN_DRAIN_TIMEOUT
        )
        for t in pending:
            t.cancel()
        if pending:
            logger.warning("%d AI task(s) cancelled at shutdown", len(pending))

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
