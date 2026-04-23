"""
Moth RSSP WebSocket 클라이언트.

Moth 프로토콜 규칙 (sub):
- Sub URL: /pang/ws/sub?channel=<type>&name=<name>&source=base&track=<track>&mode=single
- 연결 후 text frame(MIME)을 먼저 수신한 뒤 binary payload 처리
- mode=single: 30초 이내 데이터 수신 없으면 서버가 연결 종료
- WebSocket-level ping 미지원 → ping_interval=None 필수
- 연결 드롭 시 자동 재연결
- transport-level 에러는 예외로 전파 (silent fallback 없음)
- track 값: pub/sub 모두 "data" 사용 (track=streams는 ~1s 후 서버 종료)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosedError

from adapters import ADAPTER_REGISTRY, ProtocolAdapter, ParsedReport, ParsedStreamMessage
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    name: str
    moth_channel_type: str  # instant | static | dynamic
    moth_channel_name: str
    moth_track: str
    moth_source: str
    adapter: ProtocolAdapter
    platform_type: str
    is_simulator: bool = False  # True이면 시뮬레이터 채널 — 보고에 is_simulator=True 태깅


class MothChannelClient:
    """단일 Moth 채널을 구독하는 클라이언트."""

    def __init__(self, config: ChannelConfig, on_report, on_stream=None) -> None:
        self._config = config
        self._on_report = on_report  # async callback(ParsedReport)
        self._on_stream = on_stream  # async callback(ParsedStreamMessage)

    def _build_url(self) -> str:
        params = {
            "channel": self._config.moth_channel_type,
            "name": self._config.moth_channel_name,
            "source": self._config.moth_source,
            "track": self._config.moth_track,
            "mode": "single",
        }
        return f"{settings.moth_server_url}/pang/ws/sub?{urlencode(params)}"

    async def run(self) -> None:
        """재연결 루프 포함 구독 실행."""
        attempts = 0
        while True:
            try:
                await self._subscribe()
                attempts = 0
            except ConnectionClosedError as e:
                logger.warning(
                    "Channel '%s' disconnected (code=%s reason=%s), reconnecting...",
                    self._config.name,
                    e.code,
                    e.reason,
                )
            except Exception:
                logger.exception("Channel '%s' error", self._config.name)

            attempts += 1
            max_attempts = settings.reconnect_max_attempts
            if max_attempts and attempts >= max_attempts:
                logger.error(
                    "Channel '%s' max reconnect attempts reached", self._config.name
                )
                return

            await asyncio.sleep(settings.reconnect_delay_s)

    async def _subscribe(self) -> None:
        url = self._build_url()
        logger.info("Connecting to Moth channel '%s' → %s", self._config.name, url)

        # ping_interval=None: Moth 서버는 WebSocket ping에 응답하지 않음
        async with websockets.connect(url, ping_interval=None) as ws:
            logger.info("Connected: channel='%s'", self._config.name)
            current_mime: str | None = None

            async for message in ws:
                if isinstance(message, str):
                    # MIME 신호 수신
                    current_mime = message.strip()
                    logger.debug(
                        "MIME received on '%s': %s", self._config.name, current_mime
                    )
                    continue

                if isinstance(message, bytes):
                    if current_mime is None:
                        logger.warning(
                            "Binary payload received before MIME on channel '%s' — skipping",
                            self._config.name,
                        )
                        continue
                    stream_messages = self._config.adapter.parse_streams(
                        message, current_mime
                    )
                    if stream_messages:
                        if self._on_stream is None:
                            logger.warning(
                                "Stream payload received on '%s' but no stream callback is configured",
                                self._config.name,
                            )
                        else:
                            for stream_message in stream_messages:
                                await self._on_stream(stream_message)
                        continue
                    report = self._config.adapter.parse(message, current_mime)
                    if report is not None:
                        report.platform_type = (
                            report.platform_type or self._config.platform_type
                        )
                        report.name = report.name or report.platform_id
                        await self._on_report(report)
                    continue

                raise TypeError(f"Unexpected message type: {type(message)}")
