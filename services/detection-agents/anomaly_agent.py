"""
Detection - Anomaly Agent

비정상 항적 감지:
- AIS 신호 소실
- 급격한 속도 저하
- 비정상 선회율(ROT)
- 급격한 방향 변화(Heading)
- 급격한 속도 변화(Speed)
- 위치 점프(Position jump)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.events import EventType
from shared.schemas.report import PlatformReport

from config import settings
from .base import DetectionAgent

logger = logging.getLogger(__name__)

_STATE_KEY = "agent:detection_anomaly:state"
_STATE_TTL = 3600


class DetectionAnomalyAgent(DetectionAgent):
    """Detection 단계: 비정상 항적 감지"""

    agent_id = "detection-anomaly"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)

        self.config = {
            "ais_timeout_sec": settings.ais_timeout_sec,
            "speed_drop_threshold": settings.speed_drop_threshold,
            "sog_compare_max_gap_sec": settings.sog_compare_max_gap_sec,
            "rot_threshold": settings.anomaly_rot_threshold,
            "heading_threshold": settings.anomaly_heading_threshold,
            "speed_threshold": settings.anomaly_speed_threshold,
            "position_jump_threshold_nm": 5.0,
        }

        self._last_report: dict[str, PlatformReport] = {}
        self._last_seen: dict[str, datetime] = {}
        self._last_sog: dict[str, float] = {}
        self._last_sog_time: dict[str, datetime] = {}
        self._ais_lost: set[str] = set()

    async def restore_state(self) -> None:
        """서비스 재시작 시 AIS 관련 상태 복구."""
        try:
            raw = await self._redis.get(_STATE_KEY)
            if not raw:
                return

            data = json.loads(raw)
            for platform_id, ts_str in data.get("last_seen", {}).items():
                timestamp = datetime.fromisoformat(ts_str)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                self._last_seen[platform_id] = timestamp
            self._ais_lost = set(data.get("ais_lost", []))
            logger.info(
                "DetectionAnomalyAgent state restored: %d platforms, %d ais_lost",
                len(self._last_seen),
                len(self._ais_lost),
            )
        except Exception:
            logger.exception("Failed to restore DetectionAnomalyAgent state")

    async def _save_state(self) -> None:
        try:
            data = {
                "last_seen": {
                    platform_id: timestamp.isoformat()
                    for platform_id, timestamp in self._last_seen.items()
                },
                "ais_lost": sorted(self._ais_lost),
            }
            await self._redis.set(_STATE_KEY, json.dumps(data), ex=_STATE_TTL)
        except Exception:
            logger.warning("Failed to save DetectionAnomalyAgent state")

    async def on_platform_report(self, report: PlatformReport) -> None:
        """선박 위치 보고 수신."""
        import random

        platform_id = report.platform_id
        now = report.timestamp
        prev_report = self._last_report.get(platform_id)

        if platform_id in self._ais_lost:
            self._ais_lost.discard(platform_id)
            await self._save_state()

        self._last_seen[platform_id] = now

        if report.rot is not None and abs(report.rot) > self.config["rot_threshold"]:
            await self._emit_anomaly_event(
                report,
                anomaly_type="rot",
                value=report.rot,
                severity="warning",
                reason=f"비정상 선회율: {report.rot:.1f}°/min",
            )

        if prev_report and report.heading is not None and prev_report.heading is not None:
            heading_diff = abs(report.heading - prev_report.heading)
            if heading_diff > 180:
                heading_diff = 360 - heading_diff

            time_diff_sec = (report.timestamp - prev_report.timestamp).total_seconds()
            if time_diff_sec > 0:
                heading_rate = heading_diff / (time_diff_sec / 60)
                if heading_rate > self.config["heading_threshold"]:
                    await self._emit_anomaly_event(
                        report,
                        anomaly_type="heading_jump",
                        value=heading_rate,
                        severity="warning",
                        reason=f"급격한 방향 변화: {heading_rate:.1f}°/min",
                    )

        prev_sog = self._last_sog.get(platform_id)
        prev_time = self._last_sog_time.get(platform_id)
        if (
            prev_sog is not None
            and report.sog is not None
            and prev_time is not None
            and (now - prev_time).total_seconds() <= self.config["sog_compare_max_gap_sec"]
        ):
            speed_drop = prev_sog - report.sog
            if speed_drop >= self.config["speed_drop_threshold"]:
                await self._emit_anomaly_event(
                    report,
                    anomaly_type="speed_drop",
                    value=speed_drop,
                    severity="warning",
                    reason=f"급속도 저하: {prev_sog:.1f}→{report.sog:.1f}kt",
                    metadata={
                        "prev_sog": prev_sog,
                        "current_sog": report.sog,
                    },
                )

        if prev_report and report.sog is not None and prev_report.sog is not None:
            speed_diff = abs(report.sog - prev_report.sog)
            time_diff_sec = (report.timestamp - prev_report.timestamp).total_seconds()
            if time_diff_sec > 0:
                speed_rate = speed_diff / (time_diff_sec / 60)
                if speed_rate > self.config["speed_threshold"]:
                    await self._emit_anomaly_event(
                        report,
                        anomaly_type="speed_spike",
                        value=speed_rate,
                        severity="warning",
                        reason=f"급격한 속도 변화: {speed_rate:.1f}kt/min",
                    )

        if report.sog is not None:
            self._last_sog[platform_id] = report.sog
            self._last_sog_time[platform_id] = now

        if prev_report:
            distance = self._haversine_distance(
                prev_report.lat,
                prev_report.lon,
                report.lat,
                report.lon,
            )
            time_diff_min = (report.timestamp - prev_report.timestamp).total_seconds() / 60
            if time_diff_min > 0 and distance > self.config["position_jump_threshold_nm"]:
                speed_implied = distance / time_diff_min
                await self._emit_anomaly_event(
                    report,
                    anomaly_type="position_jump",
                    value=distance,
                    severity="warning",
                    reason=(
                        f"위치 점프: {distance:.1f}nm in {time_diff_min:.1f}min "
                        f"(implied speed: {speed_implied * 60:.1f}kt)"
                    ),
                )

        self._last_report[platform_id] = report
        if random.random() < 0.1:
            await self._save_state()

    async def check_ais_timeout(self) -> None:
        """주기적 호출로 AIS 소실 선박 감지."""
        now = datetime.now(tz=timezone.utc)
        state_dirty = False

        for platform_id, last_seen in list(self._last_seen.items()):
            elapsed = (now - last_seen).total_seconds()
            if elapsed <= self.config["ais_timeout_sec"] or platform_id in self._ais_lost:
                continue

            self._ais_lost.add(platform_id)
            state_dirty = True

            report = self._last_report.get(platform_id)
            await self._emit_anomaly_event(
                report,
                anomaly_type="ais_off",
                value=elapsed,
                severity="warning",
                reason=f"AIS 신호 소실 ({int(elapsed)}초 경과)",
                platform_id=platform_id,
                latitude=report.lat if report else None,
                longitude=report.lon if report else None,
            )

        if state_dirty:
            await self._save_state()

    async def _emit_anomaly_event(
        self,
        report: PlatformReport | None,
        *,
        anomaly_type: str,
        value: float,
        severity: str,
        reason: str,
        metadata: dict | None = None,
        platform_id: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> None:
        """비정상 감지 Event 발행."""
        payload = {
            "platform_id": platform_id or (report.platform_id if report else "unknown"),
            "platform_name": (report.name or report.platform_id) if report else (platform_id or "unknown"),
            "anomaly_type": anomaly_type,
            "anomaly_value": value,
            "latitude": latitude if latitude is not None else (report.lat if report else None),
            "longitude": longitude if longitude is not None else (report.lon if report else None),
            "timestamp": (
                report.timestamp.isoformat()
                if report is not None
                else datetime.now(tz=timezone.utc).isoformat()
            ),
            "reason": reason,
            "severity": severity,
        }
        if metadata:
            payload["metadata"] = metadata

        await self.emit_event(
            event_type=EventType.DETECT_ANOMALY,
            payload=payload,
            flow_id=f"detect-anomaly:{payload['platform_id']}:{anomaly_type}",
        )

    @staticmethod
    def _haversine_distance(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """Haversine으로 거리 계산 (nautical miles)."""
        import math

        radius_nm = 3440.065
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
        return radius_nm * c
