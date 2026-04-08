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
import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from ai.anomaly_ai import AnomalyAIAgent
from ai.chat_agent import ChatAgent
from ai.distress_agent import DistressAgent
from ai.llm_client import make_llm_client
from ai.report_agent import ReportAgent
from auth import require_command_role
from base import Agent, PlatformReport
from config import settings
from registry import AgentRegistry
from rule.anomaly_rule import AnomalyRuleAgent
from rule.cpa_agent import CPAAgent
from rule.zone_monitor import ZoneMonitorAgent
from shared.command_auth import CommandActor
from shared.events import alert_created_pattern, platform_report_pattern

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

_registry = AgentRegistry()
_redis: aioredis.Redis | None = None

# AI 에이전트 백그라운드 태스크 추적 집합
_pending_ai_tasks: set[asyncio.Task] = set()

# 런타임 타이밍 상수 — settings에서 읽어 모듈 초기화 시 고정
_AI_TASK_TIMEOUT = settings.ai_task_timeout_sec
_RECONNECT_MAX_DELAY = settings.reconnect_max_delay_sec
_SHUTDOWN_DRAIN_TIMEOUT = settings.shutdown_drain_timeout_sec


# ── 초기화 ──────────────────────────────────────────────────────────────────


def _setup_agents(redis: aioredis.Redis) -> None:
    agents: list[Agent] = [
        CPAAgent(redis),
        ZoneMonitorAgent(redis, settings.core_api_url),
        AnomalyRuleAgent(redis),
        AnomalyAIAgent(redis),
        DistressAgent(redis),
        ReportAgent(redis),
        ChatAgent(redis),
    ]
    for agent in agents:
        _registry.register(agent)


async def _restore_agent_states() -> None:
    """재시작 시 Redis에서 에이전트 상태 복구."""
    for agent in _registry.all():
        if hasattr(agent, "restore_state"):
            try:
                await agent.restore_state()
            except Exception:
                logger.exception("Failed to restore state for agent %s", agent.agent_id)


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
    pattern = platform_report_pattern()
    await pubsub.psubscribe(pattern)
    logger.info("Agent Runtime: subscribed to %s", pattern)

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
    if settings.ignore_simulator_reports and report.is_simulator:
        return

    rule_agents = [a for a in _registry.enabled() if a.agent_type == "rule"]
    ai_agents = [a for a in _registry.enabled() if a.agent_type == "ai"]

    # Rule Agent — 직렬 처리 (순서 보장, 빠름)
    for agent in rule_agents:
        try:
            await agent.on_platform_report(report)
        except Exception as exc:
            agent._record_error(str(exc))
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
    pattern = alert_created_pattern()
    await pubsub.psubscribe(pattern)
    logger.info("Agent Runtime: subscribed to %s", pattern)

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
    ai_agents = [a for a in _registry.enabled() if a.agent_type == "ai"]

    for agent in rule_agents:
        try:
            await agent.on_alert(alert)
        except Exception as exc:
            agent._record_error(str(exc))
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
    """AIS 타임아웃 체크 (주기: ais_check_interval_sec)."""
    while True:
        await asyncio.sleep(settings.ais_check_interval_sec)
        for agent in _registry.enabled():
            if isinstance(agent, AnomalyRuleAgent):
                await agent.check_ais_timeout()


async def _zone_reload_loop(redis: aioredis.Redis) -> None:
    """Zone 목록 주기적 재로드 (주기: zone_reload_interval_sec)."""
    for agent in _registry.all():
        if isinstance(agent, ZoneMonitorAgent):
            await agent.load_zones()
    while True:
        await asyncio.sleep(settings.zone_reload_interval_sec)
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
    await _restore_agent_states()

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
        logger.info(
            "Waiting for %d pending AI task(s) to finish...", len(_pending_ai_tasks)
        )
        done, pending = await asyncio.wait(
            _pending_ai_tasks, timeout=_SHUTDOWN_DRAIN_TIMEOUT
        )
        for t in pending:
            t.cancel()
        if pending:
            logger.warning("%d AI task(s) cancelled at shutdown", len(pending))

    if _redis is not None:
        await _redis.aclose()
    logger.info("Agent Runtime stopped")


app = FastAPI(title="CoWater Agent Runtime", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

Instrumentator().instrument(app).expose(app)


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
async def enable_agent(
    agent_id: str,
    actor: CommandActor = Depends(require_command_role("admin")),
):
    if not _registry.enable(agent_id):
        raise HTTPException(404)
    return {"agent_id": agent_id, "enabled": True}


@app.patch("/agents/{agent_id}/disable")
async def disable_agent(
    agent_id: str,
    actor: CommandActor = Depends(require_command_role("admin")),
):
    if not _registry.disable(agent_id):
        raise HTTPException(404)
    return {"agent_id": agent_id, "enabled": False}


class LevelBody(BaseModel):
    level: str


class ModelBody(BaseModel):
    model: str


class LLMConfigBody(BaseModel):
    backend: str | None = None
    model: str | None = None


class ManualRunBody(BaseModel):
    platform_id: str | None = None
    alert: dict | None = None
    dry_run: bool = False


@app.patch("/agents/{agent_id}/level")
async def set_level(
    agent_id: str,
    body: LevelBody,
    actor: CommandActor = Depends(require_command_role("admin")),
):
    if body.level not in ("L1", "L2", "L3"):
        raise HTTPException(400, "level must be L1, L2, or L3")
    if not _registry.set_level(agent_id, body.level):
        raise HTTPException(404)
    return {"agent_id": agent_id, "level": body.level}


@app.patch("/agents/{agent_id}/model")
async def set_agent_model(
    agent_id: str,
    body: ModelBody,
    actor: CommandActor = Depends(require_command_role("admin")),
):
    """개별 AI 에이전트의 LLM 모델을 런타임 변경한다."""
    agent = _registry.get(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if not hasattr(agent, "_llm"):
        raise HTTPException(400, "This agent does not use an LLM")

    backend = settings.llm_backend.lower()
    # 현재 백엔드와 동일한 클라이언트를 새 모델로 교체
    from ai.llm_client import ClaudeClient, OllamaClient, VllmClient

    try:
        if backend == "ollama":
            agent._llm = OllamaClient(  # type: ignore[attr-defined]
                base_url=settings.ollama_url,
                model=body.model,
                think=settings.ollama_think,
                timeout=settings.local_llm_timeout_sec,
                max_attempts=settings.local_llm_max_attempts,
                base_delay=settings.local_llm_base_delay_sec,
            )
        elif backend == "claude":
            agent._llm = ClaudeClient(  # type: ignore[attr-defined]
                api_key=settings.anthropic_api_key,
                model=body.model,
                timeout=settings.claude_timeout_sec,
                max_attempts=settings.claude_max_attempts,
                base_delay=settings.claude_base_delay_sec,
            )
        elif backend == "vllm":
            agent._llm = VllmClient(  # type: ignore[attr-defined]
                base_url=settings.vllm_url,
                model=body.model,
                timeout=settings.local_llm_timeout_sec,
                max_attempts=settings.local_llm_max_attempts,
                base_delay=settings.local_llm_base_delay_sec,
            )
        else:
            raise HTTPException(400, f"Unknown backend: {backend}")
    except Exception as e:
        raise HTTPException(500, str(e)) from e

    logger.info("Agent %s model changed to %s/%s", agent_id, backend, body.model)
    return {"agent_id": agent_id, "model_name": agent._llm.model_name}  # type: ignore[attr-defined]


@app.patch("/agents/{agent_id}/config")
async def set_config(
    agent_id: str,
    body: dict,
    actor: CommandActor = Depends(require_command_role("admin")),
):
    if not _registry.set_config(agent_id, body):
        raise HTTPException(404)
    return {"agent_id": agent_id, "config": body}


def _current_model_for_backend(backend: str) -> str:
    if backend == "claude":
        return settings.claude_model
    if backend == "ollama":
        return settings.ollama_model
    if backend == "vllm":
        return settings.vllm_model
    raise HTTPException(400, "backend must be claude, ollama, or vllm")


def _set_model_for_backend(backend: str, model: str) -> None:
    if backend == "claude":
        settings.claude_model = model
        return
    if backend == "ollama":
        settings.ollama_model = model
        return
    if backend == "vllm":
        settings.vllm_model = model
        return
    raise HTTPException(400, "backend must be claude, ollama, or vllm")


def _refresh_ai_llm_clients() -> int:
    refreshed = 0
    for agent in _registry.all():
        if getattr(agent, "agent_type", None) != "ai":
            continue
        if hasattr(agent, "_llm"):
            setattr(agent, "_llm", make_llm_client(settings))
            refreshed += 1
    return refreshed


@app.get("/llm")
async def get_llm_config():
    backend = settings.llm_backend
    return {
        "backend": backend,
        "model": _current_model_for_backend(backend),
        "claude_model": settings.claude_model,
        "ollama_model": settings.ollama_model,
        "vllm_model": settings.vllm_model,
    }


@app.patch("/llm")
async def set_llm_config(
    body: LLMConfigBody,
    actor: CommandActor = Depends(require_command_role("admin")),
):
    if body.backend is not None:
        if body.backend not in ("claude", "ollama", "vllm"):
            raise HTTPException(400, "backend must be claude, ollama, or vllm")
        settings.llm_backend = body.backend

    backend = settings.llm_backend
    if body.model:
        _set_model_for_backend(backend, body.model)

    refreshed = _refresh_ai_llm_clients()
    return {
        "backend": backend,
        "model": _current_model_for_backend(backend),
        "refreshed_ai_agents": refreshed,
    }


async def _latest_report_from_redis(platform_id: str) -> PlatformReport | None:
    if _redis is None:
        return None
    raw = await _redis.get(f"platform:state:{platform_id}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return PlatformReport.from_dict(data)
    except Exception:
        logger.exception(
            "Failed to deserialize latest platform state for %s", platform_id
        )
        return None


@app.post("/agents/{agent_id}/run")
async def run_agent(
    agent_id: str,
    body: ManualRunBody,
    actor: CommandActor = Depends(require_command_role("operator")),
):
    agent = _registry.get(agent_id)
    if not agent:
        raise HTTPException(404, "agent not found")
    if not agent.enabled:
        raise HTTPException(400, "agent is disabled")

    has_platform = bool(body.platform_id)
    has_alert = body.alert is not None
    if not has_platform and not has_alert:
        raise HTTPException(400, "platform_id or alert is required")

    if body.dry_run:
        return {
            "agent_id": agent_id,
            "dry_run": True,
            "will_run_on_platform": has_platform,
            "will_run_on_alert": has_alert,
        }

    if has_platform:
        platform_id = body.platform_id
        if platform_id is None:
            raise HTTPException(400, "platform_id is required")

        report = await _latest_report_from_redis(platform_id)
        if report is None:
            raise HTTPException(
                404, f"latest platform state not found for {platform_id}"
            )

        if agent.agent_type == "ai":
            _track_task(
                _safe_ai_dispatch(agent, report),
                name=f"manual-ai-report-{agent.agent_id}",
            )
        else:
            await agent.on_platform_report(report)

    if has_alert:
        if agent.agent_type == "ai":
            _track_task(
                _safe_ai_alert(agent, body.alert or {}),
                name=f"manual-ai-alert-{agent.agent_id}",
            )
        else:
            await agent.on_alert(body.alert or {})

    return {
        "agent_id": agent_id,
        "queued": True,
        "mode": {
            "platform": has_platform,
            "alert": has_alert,
        },
    }


class ChatRequest(BaseModel):
    message: str
    history: list[dict] | None = (
        None  # [{"role": "user"|"assistant", "content": "..."}, ...]
    )
    focus_platform_ids: list[str] | None = None  # 현재 주목 중인 선박 ID 목록


class UnifiedRequest(BaseModel):
    message: str
    history: list[dict] | None = None
    focus_platform_ids: list[str] | None = None
    source: str = "text"  # "text" | "voice"
    context: dict | None = None


@app.post("/chat/unified")
async def chat_unified(body: UnifiedRequest):
    """통합 채팅+명령 엔드포인트.

    - 명령어로 인식되면: command_preview 이벤트 → 프론트에서 확인 후 core에 실행 요청
    - 일반 대화이면: 스트리밍 AI 응답 (chat_stream과 동일)
    """
    agent = _registry.get("chat-agent")
    if not agent or not isinstance(agent, ChatAgent):
        raise HTTPException(404, "Chat agent not available")
    if not agent.enabled:
        raise HTTPException(400, "Chat agent is disabled")

    model_name = agent._llm.model_name

    async def generate():
        # ── 1단계: 명령어 분류 (core /commands/preview 호출) ────────────────
        is_command = False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{settings.core_api_url}/commands/preview",
                    json={"text": body.message, "source": body.source},
                )
            if resp.status_code == 200:
                is_command = True
                parsed = resp.json()
                yield f"data: {json.dumps({'type': 'command_preview', 'parsed': parsed})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            # 400 = 명령어 아님 → 대화로 처리
        except Exception:
            logger.warning("Command preview check failed, falling back to chat")

        # ── 2단계: 일반 대화 — 스트리밍 응답 ───────────────────────────────
        _ = is_command  # noqa: F841 — only used for clarity above
        try:
            async for chunk in agent.chat_stream(
                message=body.message,
                history=body.history,
                focus_platform_ids=body.focus_platform_ids,
            ):
                yield f"data: {json.dumps({'type': 'chunk', 'chunk': chunk})}\n\n"
        except Exception:
            logger.exception("Unified chat stream error")
            yield f"data: {json.dumps({'type': 'chunk', 'chunk': '[응답 오류]'})}\n\n"
        finally:
            yield f"data: {json.dumps({'type': 'done', 'model': model_name})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat")
async def chat(body: ChatRequest):
    """운항자 메시지를 받아 AI 보좌관 응답을 반환한다."""
    agent = _registry.get("chat-agent")
    if not agent or not isinstance(agent, ChatAgent):
        raise HTTPException(404, "Chat agent not available")
    if not agent.enabled:
        raise HTTPException(400, "Chat agent is disabled")

    response = await agent.chat(
        message=body.message,
        history=body.history,
        focus_platform_ids=body.focus_platform_ids,
    )
    return {
        "response": response,
        "model": agent._llm.model_name,
        "agent_id": agent.agent_id,
    }


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest):
    """SSE 스트리밍으로 AI 보좌관 응답을 반환한다 (실시간 타이핑 효과)."""
    agent = _registry.get("chat-agent")
    if not agent or not isinstance(agent, ChatAgent):
        raise HTTPException(404, "Chat agent not available")
    if not agent.enabled:
        raise HTTPException(400, "Chat agent is disabled")

    model_name = agent._llm.model_name

    async def generate():
        try:
            async for chunk in agent.chat_stream(
                message=body.message,
                history=body.history,
                focus_platform_ids=body.focus_platform_ids,
            ):
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        except Exception:
            logger.exception("Chat stream error")
            yield f"data: {json.dumps({'chunk': '[응답 오류]'})}\n\n"
        finally:
            yield f"data: {json.dumps({'done': True, 'model': model_name})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
    redis_ok = False
    core_ok = False

    try:
        if _redis is not None:
            redis_ok = bool(await _redis.ping())
    except Exception:
        logger.exception("Agent health check: Redis ping failed")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.core_api_url}/health")
            core_ok = response.is_success
    except Exception:
        logger.exception("Agent health check: core API request failed")

    agents = _registry.all()

    return {
        "status": "ok" if redis_ok and core_ok else "degraded",
        "agents": len(agents),
        "agent_counts": {
            "rule": sum(1 for agent in agents if agent.agent_type == "rule"),
            "ai": sum(1 for agent in agents if agent.agent_type == "ai"),
            "enabled": len(_registry.enabled()),
        },
        "pending_ai_tasks": len(_pending_ai_tasks),
        "dependencies": {
            "redis": "ok" if redis_ok else "error",
            "core_api": "ok" if core_ok else "error",
        },
    }
