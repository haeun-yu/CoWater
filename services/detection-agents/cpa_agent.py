"""
Detection - CPA/TCPA Agent

선박 간 최근접거리(CPA)와 최근접시간(TCPA)을 계산하여
충돌 위험을 감지하고 detect.cpa Event 발행.

COLREGS 기반:
- CPA < warning_nm  AND TCPA < warning_min  → warning
- CPA < critical_nm AND TCPA < critical_min → critical
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from shared.schemas.report import PlatformReport
from shared.events import EventType, DetectCPAPayload
from shared.config import settings

from .base import DetectionAgent

logger = logging.getLogger(__name__)

# CPA 계산에서 제외할 항법 상태
_SKIP_NAV_STATUSES = frozenset({
    "at_anchor",
    "moored",
    "aground",
    "not_under_command",
    "restricted_maneuverability",
})

# 보고 유효 기간(초)
_MAX_REPORT_AGE_SEC = 300  # 5분


class DetectionCPAAgent(DetectionAgent):
    """Detection 단계: CPA 위험 감지"""

    agent_id = "detection-cpa"

    def __init__(
        self,
        redis: aioredis.Redis,
        core_api_url: str,
        warning_cpa_nm: float = 2.0,
        warning_tcpa_min: float = 20.0,
        critical_cpa_nm: float = 0.5,
        critical_tcpa_min: float = 10.0,
    ) -> None:
        super().__init__(redis, core_api_url)

        self.config = {
            "warning_cpa_nm": warning_cpa_nm,
            "warning_tcpa_min": warning_tcpa_min,
            "critical_cpa_nm": critical_cpa_nm,
            "critical_tcpa_min": critical_tcpa_min,
        }

        # 최근 보고 캐시
        self._reports: dict[str, PlatformReport] = {}

        # 이미 경고된 쌍 (중복 방지)
        self._alerted_critical: set[frozenset] = set()
        self._alerted_warning: set[frozenset] = set()

    async def on_platform_report(self, report: PlatformReport) -> None:
        """선박 위치 보고 수신"""

        # 1. 이 선박이 CPA 계산 대상인가?
        if not self._is_active(report):
            logger.debug(
                "Platform %s skipped (nav_status=%s, sog=%s)",
                report.platform_id,
                report.nav_status,
                report.sog,
            )
            self._reports.pop(report.platform_id, None)
            return

        # 2. 이전 보고와의 시간 차이 확인
        prev_report = self._reports.get(report.platform_id)
        if prev_report:
            age_sec = (report.time - prev_report.time).total_seconds()
            if age_sec > _MAX_REPORT_AGE_SEC:
                logger.debug(
                    "Stale data for %s: %.0fs old",
                    report.platform_id,
                    age_sec,
                )
                return

        # 3. 최근 보고 저장
        self._reports[report.platform_id] = report

        # 4. 다른 모든 선박과 CPA 계산
        for other_id, other_report in list(self._reports.items()):
            if other_id >= report.platform_id:  # 중복 방지
                continue

            if not self._is_active(other_report):
                continue

            # 보고 타이밍 확인
            age_sec = (report.time - other_report.time).total_seconds()
            if age_sec > _MAX_REPORT_AGE_SEC:
                continue

            # CPA/TCPA 계산
            cpa_nm, tcpa_min = self._calculate_cpa_tcpa(report, other_report)

            if cpa_nm is None or tcpa_min is None:
                continue

            # 5. 위험 판정
            severity = self._classify_risk(cpa_nm, tcpa_min)

            if severity:
                await self._emit_cpa_event(
                    report,
                    other_report,
                    cpa_nm,
                    tcpa_min,
                    severity,
                )

    # ─────────────────────────────────────────────────────────────────────────
    # CPA/TCPA 계산
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _nautical_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Haversine 공식으로 거리 계산 (해리)"""
        R = 3440.065  # Earth radius in nautical miles

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad)
            * math.cos(lat2_rad)
            * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        return R * c

    def _calculate_cpa_tcpa(
        self, report1: PlatformReport, report2: PlatformReport
    ) -> tuple[Optional[float], Optional[float]]:
        """
        CPA(Closest Point of Approach)와 TCPA(Time to CPA) 계산.

        반환: (cpa_nm, tcpa_minutes) 또는 (None, None)
        """

        # 현재 거리
        dist_nm = self._nautical_distance(
            report1.lat, report1.lon, report2.lat, report2.lon
        )

        # 상대 위치 벡터 (보트 1 → 보트 2, 해리)
        dx = self._nautical_distance(report1.lat, report1.lon, report1.lat, report2.lon)
        dy = self._nautical_distance(report1.lat, report1.lon, report2.lat, report1.lon)

        # 방향 보정
        if report2.lon < report1.lon:
            dx = -dx
        if report2.lat < report1.lat:
            dy = -dy

        # 속도 벡터 (knots)
        if report1.cog is None or report1.sog is None:
            return None, None
        if report2.cog is None or report2.sog is None:
            return None, None

        v1x = report1.sog * math.sin(math.radians(report1.cog))
        v1y = report1.sog * math.cos(math.radians(report1.cog))

        v2x = report2.sog * math.sin(math.radians(report2.cog))
        v2y = report2.sog * math.cos(math.radians(report2.cog))

        # 상대 속도 벡터
        dvx = v1x - v2x
        dvy = v1y - v2y
        dv_mag_sq = dvx ** 2 + dvy ** 2

        if dv_mag_sq == 0:
            # 평행 운동
            return dist_nm, float('inf')

        # 최근접까지의 시간
        dot = dx * dvx + dy * dvy
        tcpa_hours = -dot / dv_mag_sq

        if tcpa_hours < 0:
            # 이미 멀어지는 중
            return dist_nm, float('inf')

        # 최근접 거리
        cpa_nm_sq = (dx + tcpa_hours * dvx) ** 2 + (dy + tcpa_hours * dvy) ** 2
        cpa_nm = math.sqrt(max(0, cpa_nm_sq))

        tcpa_min = tcpa_hours * 60

        return cpa_nm, tcpa_min

    def _classify_risk(self, cpa_nm: float, tcpa_min: float) -> Optional[str]:
        """
        CPA/TCPA에 따라 위험도 분류.

        Returns: "critical" | "warning" | None
        """
        if (
            cpa_nm < self.config["critical_cpa_nm"]
            and tcpa_min < self.config["critical_tcpa_min"]
        ):
            return "critical"

        if (
            cpa_nm < self.config["warning_cpa_nm"]
            and tcpa_min < self.config["warning_tcpa_min"]
        ):
            return "warning"

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Event 발행
    # ─────────────────────────────────────────────────────────────────────────

    async def _emit_cpa_event(
        self,
        report1: PlatformReport,
        report2: PlatformReport,
        cpa_nm: float,
        tcpa_min: float,
        severity: str,
    ) -> None:
        """CPA 위험 Event 발행"""

        # Event payload 구성 (필수 데이터만 포함)
        payload = {
            "platform_id": report1.platform_id,
            "target_platform_id": report2.platform_id,
            "cpa_minutes": tcpa_min,
            "tcpa_minutes": tcpa_min,
            "latitude": report1.lat,
            "longitude": report1.lon,
            "platform_name": report1.platform_id,  # DB에서 실제 이름 미리 로드 필요
            "target_name": report2.platform_id,
            "platform_sog": report1.sog,
            "platform_cog": report1.cog,
            "target_sog": report2.sog,
            "target_cog": report2.cog,
            "severity": severity,
            "timestamp": report1.time.isoformat(),
        }

        # Event 발행
        event_type = EventType.DETECT_CPA
        flow_id = f"cpa:{sorted([report1.platform_id, report2.platform_id])[0]}"

        await self.emit_event(
            event_type=event_type,
            payload=payload,
            flow_id=flow_id,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 유틸
    # ─────────────────────────────────────────────────────────────────────────

    def _is_active(self, report: PlatformReport) -> bool:
        """CPA 계산 대상인가?"""
        if report.nav_status in _SKIP_NAV_STATUSES:
            return False
        if report.sog is None or report.sog <= 0:
            return False
        if report.cog is None:
            return False
        return True

    def _can_process_with_partial_data(
        self, payload: dict, missing: list[str]
    ) -> bool:
        """
        platform_history, zone_context 없이도 처리 가능.
        필수 필드(platform_id, target_id, lat, lon 등)만 있으면 됨.
        """
        critical_fields = [
            "platform_id",
            "target_platform_id",
            "latitude",
            "longitude",
        ]
        return all(f in payload for f in critical_fields)
