"""
Detection - Zone Agent

구역 침입/이탈 감지:
- Prohibited 구역 침입 → critical alert
- Restricted 구역 침입 → warning alert
- 구역 이탈 → info alert
"""

from __future__ import annotations

import json
import logging

import httpx
import redis.asyncio as aioredis
from shapely.geometry import Point, shape

from shared.schemas.report import PlatformReport
from shared.events import EventType
from config import settings
from .base import DetectionAgent

logger = logging.getLogger(__name__)

_ALERT_TYPES = {"prohibited", "restricted"}


class DetectionZoneAgent(DetectionAgent):
    """Detection 단계: 구역 침입/이탈 감지"""

    agent_id = "detection-zone"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)

        self._zones: list[dict] = []
        self._zone_shapes: dict[str, object] = {}  # zone_id → Shapely geometry
        self._inside: dict[str, set[str]] = {}  # platform_id → {zone_id, ...}

    async def on_platform_report(self, report: PlatformReport) -> None:
        """선박 위치 보고 수신"""

        # 구역이 아직 로드되지 않았으면 로드
        if not self._zones:
            await self.load_zones()

        if not self._zones:
            return

        platform_id = report.platform_id
        pt = Point(report.lon, report.lat)

        for zone in self._zones:
            if zone.get("zone_type") not in _ALERT_TYPES:
                continue
            if not zone.get("active", True):
                continue

            zone_id = zone["zone_id"]
            geom = self._zone_shapes.get(zone_id)
            if geom is None:
                continue

            inside = geom.contains(pt)
            prev_inside = zone_id in self._inside.get(platform_id, set())

            # 신규 진입
            if inside and not prev_inside:
                self._inside.setdefault(platform_id, set()).add(zone_id)
                await self._emit_zone_event(
                    report,
                    zone,
                    event_type="intrusion",
                    severity="critical" if zone["zone_type"] == "prohibited" else "warning",
                )

            # 이탈
            elif not inside and prev_inside:
                self._inside.get(platform_id, set()).discard(zone_id)
                await self._emit_zone_event(
                    report,
                    zone,
                    event_type="exit",
                    severity="info",
                )

    async def load_zones(self) -> None:
        """Core API에서 Zone 목록 로드"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._core_api_url}/zones")
                resp.raise_for_status()

                zones = resp.json()
                self._zones = zones
                self._zone_shapes = {}

                for zone in zones:
                    zone_id = zone.get("zone_id")
                    if not zone_id:
                        continue

                    try:
                        self._zone_shapes[zone_id] = shape(zone.get("geometry"))
                    except Exception as e:
                        logger.warning("Failed to parse geometry for zone %s: %s", zone_id, e)

                logger.info("Loaded %d zones", len(self._zones))
        except Exception as e:
            logger.error("Failed to load zones: %s", e)

    async def _emit_zone_event(
        self,
        report: PlatformReport,
        zone: dict,
        event_type: str,
        severity: str,
    ) -> None:
        """구역 Event 발행"""

        payload = {
            "platform_id": report.platform_id,
            "platform_name": report.platform_id,
            "zone_id": zone.get("zone_id"),
            "zone_name": zone.get("name", "Unknown"),
            "zone_type": zone.get("zone_type"),
            "latitude": report.lat,
            "longitude": report.lon,
            "timestamp": report.time.isoformat(),
            "event_type": event_type,
            "severity": severity,
        }

        await self.emit_event(
            event_type=EventType.DETECT_ZONE,
            payload=payload,
        )
