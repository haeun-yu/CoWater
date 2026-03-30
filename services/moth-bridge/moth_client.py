"""
Moth RSSP WebSocket 클라이언트.

SKILL.md 가이드라인 준수:
- MIME text 메시지를 먼저 수신한 후 binary payload를 처리
- 연결 드롭 시 자동 재연결
- transport-level 에러는 예외로 전파 (silent fallback 없음)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import websockets
from websockets.exceptions import ConnectionClosedError

from adapters import ADAPTER_REGISTRY, ProtocolAdapter, ParsedReport
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    name: str
    moth_channel_type: str      # instant | static | dynamic
    moth_channel_name: str
    moth_track: str
    moth_source: str
    adapter: ProtocolAdapter
    platform_type: str


class MothChannelClient:
    """단일 Moth 채널을 구독하는 클라이언트."""

    def __init__(self, config: ChannelConfig, on_report) -> None:
        self._config = config
        self._on_report = on_report     # async callback(ParsedReport)

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
                    self._config.name, e.code, e.reason,
                )
            except Exception:
                logger.exception("Channel '%s' error", self._config.name)

            attempts += 1
            max_attempts = settings.reconnect_max_attempts
            if max_attempts and attempts >= max_attempts:
                logger.error("Channel '%s' max reconnect attempts reached", self._config.name)
                return

            await asyncio.sleep(settings.reconnect_delay_s)

    async def _subscribe(self) -> None:
        url = self._build_url()
        logger.info("Connecting to Moth channel '%s' → %s", self._config.name, url)

        async with websockets.connect(url) as ws:
            logger.info("Connected: channel='%s'", self._config.name)
            current_mime: str | None = None

            async for message in ws:
                if isinstance(message, str):
                    # MIME 신호 수신
                    current_mime = message.strip()
                    logger.debug("MIME received on '%s': %s", self._config.name, current_mime)
                    continue

                if isinstance(message, bytes):
                    if current_mime is None:
                        raise RuntimeError(
                            f"Binary payload received before MIME on channel '{self._config.name}'"
                        )
                    report = self._config.adapter.parse(message, current_mime)
                    if report is not None:
                        await self._on_report(report)
                    continue

                raise TypeError(f"Unexpected message type: {type(message)}")
