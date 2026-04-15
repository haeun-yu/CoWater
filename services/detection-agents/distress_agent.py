"""
Detection - Distress Agent

조난 신호 감지:
- SART (Search and Rescue Transponder)
- EPIRB (Emergency Position Indicating Radio Beacon)
- MAYDAY 신호
- PAN 신호 (긴급 신호)
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from shared.schemas.report import PlatformReport
from shared.events import EventType
from base import DetectionAgent

logger = logging.getLogger(__name__)

# Distress 신호를 나타내는 nav_status 또는 특수 플래그
_DISTRESS_NAV_STATUSES = frozenset({
    "distress",
    "sart_active",
})


class DetectionDistressAgent(DetectionAgent):
    """Detection 단계: 조난 신호 감지"""

    agent_id = "detection-distress"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)

        # 이미 경고된 선박 (중복 방지)
        self._alerted: set[str] = set()

    async def on_platform_report(self, report: PlatformReport) -> None:
        """선박 위치 보고 수신"""

        platform_id = report.platform_id

        # 조난 신호 확인
        is_distress = self._is_distress(report)

        if is_distress and platform_id not in self._alerted:
            # 신규 조난 신호
            self._alerted.add(platform_id)

            distress_type = self._get_distress_type(report)
            await self._emit_distress_event(report, distress_type)

        elif not is_distress and platform_id in self._alerted:
            # 조난 신호 해제
            self._alerted.discard(platform_id)
            # TODO: distress cleared event

    def _is_distress(self, report: PlatformReport) -> bool:
        """조난 신호 여부 확인"""

        # nav_status로 판단
        if report.nav_status in _DISTRESS_NAV_STATUSES:
            return True

        # 추후 추가: metadata에 distress 플래그 등
        return False

    @staticmethod
    def _get_distress_type(report: PlatformReport) -> str:
        """조난 신호 타입 결정"""
        nav_status = report.nav_status or ""

        if "sart" in nav_status.lower():
            return "sart"
        if "epirb" in nav_status.lower():
            return "epirb"

        # 기본값
        return "distress"

    async def _emit_distress_event(
        self,
        report: PlatformReport,
        distress_type: str,
    ) -> None:
        """조난 신호 Event 발행"""

        payload = {
            "platform_id": report.platform_id,
            "platform_name": report.name or report.platform_id,
            "distress_type": distress_type,
            "latitude": report.lat,
            "longitude": report.lon,
            "timestamp": report.timestamp.isoformat(),
        }

        await self.emit_event(
            event_type=EventType.DETECT_DISTRESS,
            payload=payload,
        )
