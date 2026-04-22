"""
Moth publisher for CoWater device stream JSON messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosedError

from config import settings
from shared.schemas.device_stream import DeviceStreamMessage

logger = logging.getLogger(__name__)

_MIME = "application/vnd.cowater.device-stream+json"
_PING_INTERVAL = 25.0


class DeviceStreamMothPublisher:
    """Publish normalized device stream messages to a dedicated Moth channel."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[DeviceStreamMessage] = asyncio.Queue(maxsize=1024)
        self._connected = False

    def _build_url(self) -> str:
        params = {
            "channel": settings.stream_moth_channel_type,
            "name": settings.stream_moth_channel_name,
            "source": "base",
            "track": settings.stream_moth_track,
            "mode": "single",
        }
        return f"{settings.moth_server_url}/pang/ws/pub?{urlencode(params)}"

    async def publish_stream(self, message: DeviceStreamMessage) -> None:
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning(
                "Device stream publish queue full - dropping %s for %s",
                message.envelope.stream,
                message.envelope.device_id,
            )

    async def run(self) -> None:
        while True:
            try:
                await self._publish_loop()
            except ConnectionClosedError as exc:
                logger.warning(
                    "Device stream Moth connection closed (code=%s), reconnecting...",
                    exc.code,
                )
            except Exception:
                logger.exception("Device stream Moth publisher error, reconnecting...")
            self._connected = False
            await asyncio.sleep(settings.reconnect_delay_s)

    async def _publish_loop(self) -> None:
        url = self._build_url()
        logger.info("Device stream Moth publisher connecting -> %s", url)

        async with websockets.connect(url) as ws:
            self._connected = True
            logger.info("Device stream Moth publisher connected")

            await ws.send(_MIME)
            last_ping_at = asyncio.get_running_loop().time()
            sent_count = 0

            while True:
                now = asyncio.get_running_loop().time()
                if now - last_ping_at >= _PING_INTERVAL:
                    await ws.ping()
                    last_ping_at = now

                try:
                    message = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                    payload = json.dumps(message.to_dict(), separators=(",", ":"))
                    await ws.send(payload.encode("utf-8"))
                    last_ping_at = now
                    sent_count += 1
                    if sent_count % 25 == 0:
                        logger.debug(
                            "Device stream Moth publisher sent %d messages",
                            sent_count,
                        )
                except asyncio.TimeoutError:
                    pass
