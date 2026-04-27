"""WebSocket 연결 관리 및 브로드캐스트."""

import asyncio
import json
import logging
from typing import Literal

from fastapi import WebSocket

logger = logging.getLogger(__name__)

Topic = Literal["platforms", "alerts", "reports", "replay", "events"]


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[Topic, set[WebSocket]] = {
            "platforms": set(),
            "alerts": set(),
            "reports": set(),
            "replay": set(),
            "events": set(),
        }
        self._lock = asyncio.Lock()
        self._broadcast_success_count: dict[Topic, int] = {
            "platforms": 0,
            "alerts": 0,
            "reports": 0,
            "replay": 0,
            "events": 0,
        }
        self._broadcast_failure_count: dict[Topic, int] = {
            "platforms": 0,
            "alerts": 0,
            "reports": 0,
            "replay": 0,
            "events": 0,
        }

    async def connect(self, ws: WebSocket, topic: Topic) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[topic].add(ws)
        logger.debug(
            "WS connected: topic=%s total=%d", topic, len(self._connections[topic])
        )

    async def disconnect(self, ws: WebSocket, topic: Topic) -> None:
        async with self._lock:
            self._connections[topic].discard(ws)

    async def broadcast(self, topic: Topic, payload: dict) -> None:
        message = json.dumps(payload)
        dead: set[WebSocket] = set()

        async with self._lock:
            connections = list(self._connections[topic])

        for ws in connections:
            try:
                await ws.send_text(message)
                self._broadcast_success_count[topic] += 1
            except Exception:
                dead.add(ws)
                self._broadcast_failure_count[topic] += 1

        if dead:
            async with self._lock:
                self._connections[topic] -= dead
            logger.debug("WS removed %d dead client(s) for topic=%s", len(dead), topic)

    def connection_count(self, topic: Topic) -> int:
        return len(self._connections[topic])

    def stats(self) -> dict[str, dict[str, int]]:
        return {
            topic: {
                "connections": len(self._connections[topic]),
                "broadcast_success": self._broadcast_success_count[topic],
                "broadcast_failure": self._broadcast_failure_count[topic],
            }
            for topic in self._connections
        }


hub = WebSocketHub()
