"""
Moth publisher for CoWater device stream JSON messages.

Moth 프로토콜 규칙 (pub):
- Pub URL: /pang/ws/pub?channel=<type>&name=<name>&source=base&track=<track>&mode=single
- 연결 후 MIME text frame을 먼저 전송한 뒤 binary payload 전송
- mode=single: 30초 이내 binary 데이터 전송 없으면 서버가 연결 종료
- 빈 binary frame(b'')을 25초마다 keepalive로 전송
- WebSocket-level ping 미지원 → ping_interval=None 필수
- 연결 드롭 시 자동 재연결
- track 값은 pub/sub 모두 "data" 사용 (track=streams는 ~1s 후 서버가 연결 종료)
- MIME 전송 후 즉시 binary 데이터 전송 필요 (async yield 없이)
- pub 연결에서는 recv() 금지 — send() 전용
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

        # ping_interval=None: Moth 서버는 WebSocket ping에 응답하지 않음
        async with websockets.connect(url, ping_interval=None) as ws:
            self._connected = True
            logger.info("Device stream Moth publisher connected")

            await ws.send(_MIME)
            last_sent_at = asyncio.get_running_loop().time()
            sent_count = 0

            while True:
                now = asyncio.get_running_loop().time()
                # 빈 binary frame으로 keepalive (30s 서버 타임아웃 방지)
                if now - last_sent_at >= _PING_INTERVAL:
                    await ws.send(b'')
                    last_sent_at = now

                try:
                    message = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                    payload = json.dumps(message.to_dict(), separators=(",", ":"))
                    await ws.send(payload.encode("utf-8"))
                    last_sent_at = now
                    sent_count += 1
                    if sent_count % 25 == 0:
                        logger.debug(
                            "Device stream Moth publisher sent %d messages",
                            sent_count,
                        )
                except asyncio.TimeoutError:
                    pass
