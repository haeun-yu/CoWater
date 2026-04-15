"""
Detection - Anomaly Agent

비정상 항적 감지:
- 비정상적인 선회율(ROT)
- 급격한 방향 변화(Heading)
- 급격한 속도 변화(Speed)
- 위치 점프(Position jump)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import redis.asyncio as aioredis

from shared.schemas.report import PlatformReport
from shared.events import EventType
from config import settings
from .base import DetectionAgent

logger = logging.getLogger(__name__)


class DetectionAnomalyAgent(DetectionAgent):
    """Detection 단계: 비정상 항적 감지"""

    agent_id = "detection-anomaly"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)

        self.config = {
            "rot_threshold": settings.anomaly_rot_threshold,  # degrees/min
            "heading_threshold": settings.anomaly_heading_threshold,  # degrees
            "speed_threshold": settings.anomaly_speed_threshold,  # knots
            "position_jump_threshold_nm": 5.0,  # nautical miles
        }

        # 최근 보고 캐시 (비정상 감지용)
        self._last_report: dict[str, PlatformReport] = {}

    async def on_platform_report(self, report: PlatformReport) -> None:
        """선박 위치 보고 수신"""

        platform_id = report.platform_id
        prev_report = self._last_report.get(platform_id)

        # ROT 확인 (회전율)
        if report.rot is not None:
            if abs(report.rot) > self.config["rot_threshold"]:
                await self._emit_anomaly_event(
                    report,
                    anomaly_type="rot",
                    value=report.rot,
                    reason=f"비정상 선회율: {report.rot:.1f}°/min",
                )

        # Heading 변화 확인 (이전 보고와 비교)
        if prev_report and report.heading is not None and prev_report.heading is not None:
            heading_diff = abs(report.heading - prev_report.heading)
            # 더 작은 각도 선택 (360도 기준)
            if heading_diff > 180:
                heading_diff = 360 - heading_diff

            time_diff_sec = (report.time - prev_report.time).total_seconds()
            if time_diff_sec > 0:
                heading_rate = heading_diff / (time_diff_sec / 60)  # degrees/min

                if heading_rate > self.config["heading_threshold"]:
                    await self._emit_anomaly_event(
                        report,
                        anomaly_type="heading_jump",
                        value=heading_rate,
                        reason=f"급격한 방향 변화: {heading_rate:.1f}°/min",
                    )

        # Speed 변화 확인
        if prev_report and report.sog is not None and prev_report.sog is not None:
            speed_diff = abs(report.sog - prev_report.sog)
            time_diff_sec = (report.time - prev_report.time).total_seconds()

            if time_diff_sec > 0:
                speed_rate = speed_diff / (time_diff_sec / 60)  # knots/min

                if speed_rate > self.config["speed_threshold"]:
                    await self._emit_anomaly_event(
                        report,
                        anomaly_type="speed_spike",
                        value=speed_rate,
                        reason=f"급격한 속도 변화: {speed_rate:.1f}kt/min",
                    )

        # Position jump 확인 (거리 계산)
        if prev_report:
            distance = self._haversine_distance(
                prev_report.lat, prev_report.lon, report.lat, report.lon
            )
            time_diff_min = (report.time - prev_report.time).total_seconds() / 60

            if time_diff_min > 0:
                speed_implied = distance / time_diff_min  # nautical miles/min

                if distance > self.config["position_jump_threshold_nm"]:
                    await self._emit_anomaly_event(
                        report,
                        anomaly_type="position_jump",
                        value=distance,
                        reason=f"위치 점프: {distance:.1f}nm in {time_diff_min:.1f}min (implied speed: {speed_implied*60:.1f}kt)",
                    )

        # 현재 보고 저장
        self._last_report[platform_id] = report

    async def _emit_anomaly_event(
        self,
        report: PlatformReport,
        anomaly_type: str,
        value: float,
        reason: str,
    ) -> None:
        """비정상 감지 Event 발행"""

        payload = {
            "platform_id": report.platform_id,
            "platform_name": report.platform_id,
            "anomaly_type": anomaly_type,
            "anomaly_value": value,
            "latitude": report.lat,
            "longitude": report.lon,
            "timestamp": report.time.isoformat(),
            "reason": reason,
        }

        await self.emit_event(
            event_type=EventType.DETECT_ANOMALY,
            payload=payload,
        )

    @staticmethod
    def _haversine_distance(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """Haversine으로 거리 계산 (nautical miles)"""
        import math

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
