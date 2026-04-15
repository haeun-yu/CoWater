"""
Detection - CPA/TCPA Agent

선박 간 최근접거리(CPA)와 최근접시간(TCPA)을 계산하여
충돌 위험을 감지하고 detect.cpa Event를 발행한다.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.events import EventType
from shared.schemas.report import PlatformReport

from .base import DetectionAgent

logger = logging.getLogger(__name__)

_SKIP_NAV_STATUSES = frozenset(
    {
        "at_anchor",
        "moored",
        "aground",
        "not_under_command",
        "restricted_maneuverability",
    }
)
_MAX_REPORT_AGE_SEC = 300


class DetectionCPAAgent(DetectionAgent):
    """Detection 단계: CPA 위험 감지."""

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
        self._reports: dict[str, PlatformReport] = {}
        self._alerted_critical: set[frozenset[str]] = set()
        self._alerted_warning: set[frozenset[str]] = set()

    async def on_platform_report(self, report: PlatformReport) -> None:
        self._reports[report.platform_id] = report

        if self._is_active(report):
            await self._check_all(report.platform_id)
        else:
            await self._resolve_pairs_for_platform(report.platform_id, "inactive_target")

    @staticmethod
    def _pair_and_key(id1: str, id2: str) -> tuple[frozenset[str], str]:
        platform_ids = sorted([id1, id2])
        return frozenset(platform_ids), f"detect-cpa:{platform_ids[0]}:{platform_ids[1]}"

    async def _resolve_pairs_for_platform(self, platform_id: str, reason: str) -> None:
        affected_pairs = [
            pair
            for pair in (self._alerted_warning | self._alerted_critical)
            if platform_id in pair
        ]
        for pair in affected_pairs:
            platform_ids = sorted(pair)
            await self._emit_cpa_event(
                self._reports.get(platform_ids[0]),
                self._reports.get(platform_ids[1]),
                cpa_nm=None,
                tcpa_min=None,
                severity="info",
                event_state="cleared",
                reason=reason,
            )
            self._alerted_warning.discard(pair)
            self._alerted_critical.discard(pair)

    async def _purge_stale_reports(self) -> None:
        now = datetime.now(tz=timezone.utc)
        stale_platform_ids = [
            platform_id
            for platform_id, report in self._reports.items()
            if (now - report.timestamp).total_seconds() > _MAX_REPORT_AGE_SEC
        ]
        for platform_id in stale_platform_ids:
            await self._resolve_pairs_for_platform(platform_id, "stale_report")
            self._reports.pop(platform_id, None)

    async def _check_all(self, changed_platform_id: str) -> None:
        await self._purge_stale_reports()

        report = self._reports.get(changed_platform_id)
        if report is None:
            return

        now = datetime.now(tz=timezone.utc)
        for other_platform_id, other_report in list(self._reports.items()):
            if other_platform_id == changed_platform_id:
                continue
            if not self._is_active(other_report):
                await self._resolve_pairs_for_platform(other_platform_id, "inactive_target")
                continue
            if (now - other_report.timestamp).total_seconds() > _MAX_REPORT_AGE_SEC:
                await self._resolve_pairs_for_platform(other_platform_id, "stale_report")
                continue

            cpa_nm, tcpa_min = _compute_cpa_tcpa(report, other_report)
            if cpa_nm is None or tcpa_min is None or tcpa_min < 0 or not math.isfinite(tcpa_min):
                await self._emit_cpa_event(
                    report,
                    other_report,
                    cpa_nm=None,
                    tcpa_min=None,
                    severity="info",
                    event_state="cleared",
                    reason="risk_cleared",
                )
                pair, _ = self._pair_and_key(report.platform_id, other_report.platform_id)
                self._alerted_warning.discard(pair)
                self._alerted_critical.discard(pair)
                continue

            await self._evaluate(report, other_report, cpa_nm, tcpa_min)

    async def _evaluate(
        self,
        report: PlatformReport,
        other_report: PlatformReport,
        cpa_nm: float,
        tcpa_min: float,
    ) -> None:
        pair, _ = self._pair_and_key(report.platform_id, other_report.platform_id)

        if (
            cpa_nm < self.config["critical_cpa_nm"]
            and tcpa_min < self.config["critical_tcpa_min"]
        ):
            self._alerted_warning.discard(pair)
            self._alerted_critical.add(pair)
            await self._emit_cpa_event(
                report,
                other_report,
                cpa_nm=cpa_nm,
                tcpa_min=tcpa_min,
                severity="critical",
                event_state="active",
                reason="collision_risk",
            )
            return

        if (
            cpa_nm < self.config["warning_cpa_nm"]
            and tcpa_min < self.config["warning_tcpa_min"]
        ):
            if pair not in self._alerted_warning and pair not in self._alerted_critical:
                self._alerted_warning.add(pair)
                await self._emit_cpa_event(
                    report,
                    other_report,
                    cpa_nm=cpa_nm,
                    tcpa_min=tcpa_min,
                    severity="warning",
                    event_state="active",
                    reason="collision_risk",
                )
            return

        if pair in self._alerted_warning or pair in self._alerted_critical:
            self._alerted_warning.discard(pair)
            self._alerted_critical.discard(pair)
            await self._emit_cpa_event(
                report,
                other_report,
                cpa_nm=None,
                tcpa_min=None,
                severity="info",
                event_state="cleared",
                reason="risk_cleared",
            )

    async def _emit_cpa_event(
        self,
        report: PlatformReport | None,
        other_report: PlatformReport | None,
        *,
        cpa_nm: float | None,
        tcpa_min: float | None,
        severity: str,
        event_state: str,
        reason: str,
    ) -> None:
        if report is None and other_report is None:
            return

        primary = report or other_report
        counterpart = other_report if report is not None else report
        assert primary is not None

        payload = {
            "platform_id": primary.platform_id,
            "target_platform_id": counterpart.platform_id if counterpart else None,
            "cpa_nm": cpa_nm,
            "cpa_minutes": cpa_nm,
            "tcpa_minutes": tcpa_min,
            "tcpa_min": tcpa_min,
            "latitude": primary.lat,
            "longitude": primary.lon,
            "platform_name": primary.name or primary.platform_id,
            "target_name": (
                (counterpart.name or counterpart.platform_id)
                if counterpart is not None
                else None
            ),
            "platform_sog": primary.sog,
            "platform_cog": primary.cog,
            "target_sog": counterpart.sog if counterpart else None,
            "target_cog": counterpart.cog if counterpart else None,
            "severity": severity,
            "event_state": event_state,
            "reason": reason,
            "timestamp": primary.timestamp.isoformat(),
        }

        target_platform_id = payload.get("target_platform_id") or "unknown"
        flow_platforms = sorted([payload["platform_id"], target_platform_id])

        await self.emit_event(
            event_type=EventType.DETECT_CPA,
            payload=payload,
            flow_id=f"detect-cpa:{flow_platforms[0]}:{flow_platforms[1]}",
        )

    def _is_active(self, report: PlatformReport) -> bool:
        if report.nav_status in _SKIP_NAV_STATUSES:
            return False
        if report.sog is None or report.sog <= 0:
            return False
        if report.cog is None:
            return False
        return True


_NM_PER_DEG_LAT = 60.0
_KNOTS_TO_NM_PER_MIN = 1 / 60


def _compute_cpa_tcpa(
    report: PlatformReport, other_report: PlatformReport
) -> tuple[float | None, float | None]:
    """두 선박의 위치/속도 벡터로 CPA(NM)와 TCPA(분)를 계산."""
    if report.sog is None or other_report.sog is None:
        return None, None
    if report.cog is None or other_report.cog is None:
        return None, None

    avg_lat = (report.lat + other_report.lat) / 2
    cos_lat = math.cos(math.radians(avg_lat))

    dx = (other_report.lon - report.lon) * cos_lat * _NM_PER_DEG_LAT
    dy = (other_report.lat - report.lat) * _NM_PER_DEG_LAT

    def velocity(sog: float, cog: float) -> tuple[float, float]:
        radians = math.radians(cog)
        return (
            sog * math.sin(radians) * _KNOTS_TO_NM_PER_MIN,
            sog * math.cos(radians) * _KNOTS_TO_NM_PER_MIN,
        )

    vx1, vy1 = velocity(report.sog, report.cog)
    vx2, vy2 = velocity(other_report.sog, other_report.cog)

    dvx = vx2 - vx1
    dvy = vy2 - vy1
    dv2 = dvx**2 + dvy**2
    if dv2 < 1e-9:
        return math.hypot(dx, dy), float("inf")

    tcpa_min = -((dx * dvx) + (dy * dvy)) / dv2
    cpa_x = dx + dvx * tcpa_min
    cpa_y = dy + dvy * tcpa_min
    cpa_nm = math.hypot(cpa_x, cpa_y)
    return cpa_nm, tcpa_min
