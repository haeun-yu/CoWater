"""
프론트엔드 직접 연결용 WebSocket relay.

moth-bridge가 파싱한 ParsedReport를 Redis/Core를 거치지 않고
연결된 브라우저 클라이언트에 직접 브로드캐스트한다.

지연 경로:
  기존: Moth → moth-bridge → Redis → core consumer → WebSocket → Frontend
  신규: Moth → moth-bridge → WebSocket → Frontend  (Redis 경유 없음)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

from shared.events import build_event

if TYPE_CHECKING:
    from adapters.base import ParsedReport

logger = logging.getLogger(__name__)

app = FastAPI(title="CoWater Moth-Bridge Relay", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_clients: set[WebSocket] = set()
_lock = asyncio.Lock()
_redis: aioredis.Redis | None = None
_expected_channels = 0
_publish_success_count = 0
_publish_failure_count = 0
_last_report_at: str | None = None
_last_broadcast_at: str | None = None
_broadcast_success_count = 0
_broadcast_failure_count = 0


def attach_redis(redis: aioredis.Redis) -> None:
    global _redis
    _redis = redis


def set_expected_channels(count: int) -> None:
    global _expected_channels
    _expected_channels = count


def track_report_activity(report: "ParsedReport") -> None:
    global _last_report_at
    _last_report_at = report.timestamp.isoformat()


def track_publish_result(success: bool) -> None:
    global _publish_success_count, _publish_failure_count
    if success:
        _publish_success_count += 1
    else:
        _publish_failure_count += 1


def _stream_state() -> str:
    if _last_report_at is None:
        return "idle"

    age = (
        datetime.now(timezone.utc)
        - datetime.fromisoformat(_last_report_at).astimezone(timezone.utc)
    ).total_seconds()
    return "ok" if age <= 60 else "stale"


async def broadcast(report: "ParsedReport") -> None:
    """파싱된 ParsedReport를 연결된 모든 프론트엔드 클라이언트에 전송."""
    if not _clients:
        return

    payload = json.dumps(
        {
            "type": "position_update",
            "event": build_event(
                "position_update",
                "moth-bridge-relay",
                produced_at=report.timestamp.isoformat(),
            ),
            "platform_id": report.platform_id,
            "platform_type": report.platform_type,
            "name": report.name,
            "timestamp": report.timestamp.isoformat(),
            "schema_version": 1,
            "source": "moth-bridge-relay",
            "lat": report.position.lat,
            "lon": report.position.lon,
            "sog": report.sog,
            "cog": report.cog,
            "heading": report.heading,
            "rot": report.rot,
            "nav_status": report.nav_status,
            "source_protocol": report.source_protocol,
        }
    )

    global _broadcast_success_count, _broadcast_failure_count

    async with _lock:
        clients = list(_clients)

    dead: set[WebSocket] = set()
    for ws in clients:
        try:
            await ws.send_text(payload)
            _broadcast_success_count += 1
        except Exception:
            dead.add(ws)
            _broadcast_failure_count += 1

    if dead:
        async with _lock:
            _clients.difference_update(dead)
        logger.debug("Removed %d dead WS client(s)", len(dead))

    global _last_broadcast_at
    _last_broadcast_at = datetime.now(timezone.utc).isoformat()


@app.websocket("/ws/positions")
async def ws_positions(ws: WebSocket) -> None:
    await ws.accept()
    async with _lock:
        _clients.add(ws)
    logger.info("WS client connected (total=%d)", len(_clients))
    try:
        while True:
            # ping/pong — 브라우저 연결 유지
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with _lock:
            _clients.discard(ws)
        logger.info("WS client disconnected (total=%d)", len(_clients))


@app.get("/health")
async def health() -> dict:
    redis_ok = False
    if _redis is not None:
        try:
            redis_ok = bool(await _redis.ping())
        except Exception:
            logger.exception("Relay health check: Redis ping failed")

    stream_state = _stream_state()
    return {
        "status": "ok" if redis_ok and stream_state in {"ok", "idle"} else "degraded",
        "transport": "websocket-relay",
        "clients": len(_clients),
        "expected_channels": _expected_channels,
        "publish_counts": {
            "success": _publish_success_count,
            "failure": _publish_failure_count,
        },
        "broadcast_counts": {
            "success": _broadcast_success_count,
            "failure": _broadcast_failure_count,
        },
        "last_report_at": _last_report_at,
        "last_broadcast_at": _last_broadcast_at,
        "dependencies": {
            "redis": "ok" if redis_ok else "error",
            "report_stream": stream_state,
        },
    }
