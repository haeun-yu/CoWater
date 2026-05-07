"""
Moth Publisher: Registry 및 System Agent 데이터를 Moth 서버에 발행

주요 채널:
- overview: System Agent 상태 (매 변경 시)
- missions: 모든 미션 목록 (매 변경 시)
- mission.{mission_id}: 특정 미션 상세 (매 변경 시)
- events: 이벤트 목록 (매 발생 시)
- alerts: 알림 목록 (매 생성/변경 시)
- insights: 인사이트 목록 (매 변경 시)
- policies: 정책 목록 (매 변경 시)
- approvals: 승인 목록 (매 변경 시)
- mission_proposals: 미션 제안 목록 (매 변경 시)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from urllib.parse import urlunsplit, urlsplit

try:
    import websockets
except ImportError:
    websockets = None

logger = logging.getLogger(__name__)


def _build_publish_url(base_url: str, channel: str) -> str:
    """Moth 발행 URL 생성"""
    parsed = urlsplit(base_url)
    path = "/pang/ws/meb"
    query = f"channel=instant&name={channel}&source=registry&track=registry"
    return urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))


class MothPublisher:
    """Moth 서버에 메시지를 발행하는 클라이언트"""

    def __init__(self, moth_base_url: str = "wss://cobot.center:8287"):
        """
        Args:
            moth_base_url: Moth 기본 URL (예: wss://cobot.center:8287)
        """
        if websockets is None:
            logger.warning("websockets not installed - Moth publishing disabled")
            self.enabled = False
            return

        self.enabled = True
        self.moth_base_url = moth_base_url
        self.connections: dict[str, Any] = {}  # channel -> websocket
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, payload: Any) -> bool:
        """
        채널에 메시지 발행 (비동기 백그라운드)

        Args:
            channel: 채널 이름 (예: "missions", "events", "overview")
            payload: 발행할 데이터 (dict 또는 list)

        Returns:
            성공 여부
        """
        if not self.enabled:
            return False

        # 비동기 발행 (블로킹 없음)
        asyncio.create_task(self._publish_async(channel, payload))
        return True

    async def _publish_async(self, channel: str, payload: Any) -> None:
        """비동기 발행 구현"""
        try:
            ws_url = _build_publish_url(self.moth_base_url, channel)

            async with websockets.connect(ws_url) as ws:
                # 연결 후 메시지 발행
                message = {
                    "type": "publish",
                    "channel": channel,
                    "data": payload,
                }
                await ws.send(json.dumps(message))
                logger.debug(f"[Moth] Published to {channel}")

        except Exception as e:
            logger.debug(f"[Moth] Publish error on {channel}: {e}")

    async def close_all(self) -> None:
        """모든 연결 종료"""
        for ws in self.connections.values():
            try:
                await ws.close()
            except Exception:
                pass
        self.connections.clear()


# 글로벌 publisher 인스턴스
_publisher: Optional[MothPublisher] = None


def get_publisher() -> MothPublisher:
    """글로벌 publisher 인스턴스 획득"""
    global _publisher
    if _publisher is None:
        _publisher = MothPublisher()
    return _publisher


async def publish_to_moth(channel: str, payload: Any) -> bool:
    """편의 함수: 글로벌 publisher에 발행"""
    return await get_publisher().publish(channel, payload)
