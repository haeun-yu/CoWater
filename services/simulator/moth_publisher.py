"""
Moth RSSP WebSocket 퍼블리셔.

Moth 프로토콜 규칙 (pub):
- Pub URL: /pang/ws/pub?channel=<type>&name=<name>&source=base&track=<track>&mode=single
- 연결 후 MIME text frame을 먼저 전송한 뒤 binary payload 전송
- mode=single: 30초 이내 binary 데이터 전송 없으면 서버가 연결 종료
- 빈 binary frame(b'')을 25초마다 keepalive로 전송
- WebSocket-level ping 미지원 → ping_interval=None 필수
- 연결 드롭 시 자동 재연결
- track 값: "data" 사용 (track=streams는 ~1s 후 서버 종료)
- MIME 전송 후 즉시 binary 전송 (async yield 없이)
- pub 연결에서는 recv() 금지
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosedError

from config import settings

logger = logging.getLogger(__name__)

_MIME = "text/plain"
_PING_INTERVAL = 25.0  # seconds - send ping before 30s idle timeout


class MothPublisher:
    """
    Moth 채널에 AIS NMEA 문장을 퍼블리시.
    단일 채널 전용 — 여러 채널이 필요하면 인스턴스를 여러 개 생성.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=512)
        self._connected = False

    def _build_url(self) -> str:
        params = {
            "channel": settings.moth_channel_type,
            "name": settings.moth_channel_name,
            "source": "base",
            "track": settings.moth_track,
            "mode": "single",
        }
        return f"{settings.moth_server_url}/pang/ws/pub?{urlencode(params)}"

    async def publish(self, nmea_sentence: str) -> None:
        """AIS 문장을 큐에 넣는다 (논블로킹)."""
        try:
            self._queue.put_nowait(nmea_sentence)
        except asyncio.QueueFull:
            logger.warning("Publish queue full — dropping frame")

    async def run(self) -> None:
        """재연결 루프 포함 퍼블리시 실행. 메인 태스크로 실행."""
        while True:
            try:
                await self._publish_loop()
            except ConnectionClosedError as e:
                logger.warning("Moth connection closed (code=%s), reconnecting...", e.code)
            except Exception:
                logger.exception("Moth publisher error, reconnecting...")
            self._connected = False
            await asyncio.sleep(settings.reconnect_delay_s if hasattr(settings, "reconnect_delay_s") else 5.0)

    async def _publish_loop(self) -> None:
        url = self._build_url()
        logger.info("Moth publisher connecting → %s", url)

        # ping_interval=None: Moth 서버는 WebSocket ping에 응답하지 않음
        async with websockets.connect(url, ping_interval=None) as ws:
            self._connected = True
            logger.info("Moth publisher connected")

            # 초기 MIME 전송 (한 번만)
            await ws.send(_MIME)
            last_sent_at = asyncio.get_running_loop().time()
            sent_count = 0

            while True:
                now = asyncio.get_running_loop().time()

                # 빈 binary frame으로 keepalive (30s 서버 타임아웃 방지)
                if now - last_sent_at >= _PING_INTERVAL:
                    await ws.send(b'')
                    last_sent_at = now
                    logger.debug("Moth publisher sent keepalive")

                # 큐에서 메시지 꺼내기 (최대 100ms 대기)
                try:
                    sentence = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                    await ws.send(sentence.encode("ascii"))
                    last_sent_at = now
                    sent_count += 1
                    if sent_count % 15 == 0:
                        logger.debug("Moth publisher sent %d sentences", sent_count)
                except asyncio.TimeoutError:
                    pass
