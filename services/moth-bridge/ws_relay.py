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
from typing import TYPE_CHECKING

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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


async def broadcast(report: "ParsedReport") -> None:
    """파싱된 ParsedReport를 연결된 모든 프론트엔드 클라이언트에 전송."""
    if not _clients:
        return

    payload = json.dumps(
        {
            "type": "position_update",
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

    dead: set[WebSocket] = set()
    for ws in list(_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)

    if dead:
        async with _lock:
            _clients.difference_update(dead)
        logger.debug("Removed %d dead WS client(s)", len(dead))


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
    return {"status": "ok", "transport": "websocket-relay", "clients": len(_clients)}
