"""WebSocket 연결 관리 및 브로드캐스트."""

import asyncio
import json
import logging
from typing import Literal

from fastapi import WebSocket

logger = logging.getLogger(__name__)

Topic = Literal["platforms", "alerts", "replay"]


class WebSocketHub:
    def __init__(self) -> None:
        self._connections: dict[Topic, set[WebSocket]] = {
            "platforms": set(),
            "alerts": set(),
            "replay": set(),
        }
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, topic: Topic) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[topic].add(ws)
        logger.debug("WS connected: topic=%s total=%d", topic, len(self._connections[topic]))

    async def disconnect(self, ws: WebSocket, topic: Topic) -> None:
        async with self._lock:
            self._connections[topic].discard(ws)

    async def broadcast(self, topic: Topic, payload: dict) -> None:
        message = json.dumps(payload)
        dead: set[WebSocket] = set()

        for ws in list(self._connections[topic]):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        if dead:
            async with self._lock:
                self._connections[topic] -= dead

    def connection_count(self, topic: Topic) -> int:
        return len(self._connections[topic])


hub = WebSocketHub()
