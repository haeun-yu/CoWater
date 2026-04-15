"""
Detection - Zone Agent

구역 침입/이탈 감지:
- 금지구역 침입
- 제한구역 침입
- 구역 이탈
"""

from __future__ import annotations

import json
import logging

import httpx
import redis.asyncio as aioredis
from shapely.geometry import Point, shape

from shared.events import EventType
from shared.schemas.report import PlatformReport

from base import DetectionAgent

logger = logging.getLogger(__name__)

_ALERT_TYPES = {"prohibited", "restricted"}
_STATE_KEY = "agent:detection_zone:inside"
_STATE_TTL = 3600


class DetectionZoneAgent(DetectionAgent):
    """Detection 단계: 구역 침입/이탈 감지"""

    agent_id = "detection-zone"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis, core_api_url)
        self._zones: list[dict] = []
        self._zone_shapes: dict[str, object] = {}
        self._inside: dict[str, set[str]] = {}

    async def restore_state(self) -> None:
        try:
            raw = await self._redis.get(_STATE_KEY)
            if not raw:
                return

            data = json.loads(raw)
            self._inside = {
                platform_id: set(zone_ids)
                for platform_id, zone_ids in data.items()
            }
            logger.info(
                "DetectionZoneAgent state restored: %d platforms inside zones",
                len(self._inside),
            )
        except Exception:
            logger.exception("Failed to restore DetectionZoneAgent state")

    async def _save_state(self) -> None:
        try:
            data = {
                platform_id: sorted(zone_ids)
                for platform_id, zone_ids in self._inside.items()
                if zone_ids
            }
            await self._redis.set(_STATE_KEY, json.dumps(data), ex=_STATE_TTL)
        except Exception:
            logger.warning("Failed to save DetectionZoneAgent state")

    async def load_zones(self) -> None:
        """Core API에서 활성 Zone 목록 로드."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._core_api_url}/zones")
                response.raise_for_status()

            zones = response.json()
            self._zones = zones
            self._zone_shapes = {}
            valid_zone_ids = set()

            for zone in zones:
                zone_id = zone.get("zone_id")
                if not zone_id:
                    continue
                valid_zone_ids.add(zone_id)
                try:
                    self._zone_shapes[zone_id] = shape(zone.get("geometry"))
                except Exception as exc:
                    logger.warning("Failed to parse geometry for zone %s: %s", zone_id, exc)

            for platform_id in list(self._inside.keys()):
                invalid_zone_ids = self._inside[platform_id] - valid_zone_ids
                if invalid_zone_ids:
                    self._inside[platform_id] -= invalid_zone_ids
                    if not self._inside[platform_id]:
                        del self._inside[platform_id]

            await self._save_state()
            logger.info("Loaded %d zones", len(self._zones))
        except Exception as exc:
            logger.error("Failed to load zones: %s", exc)

    async def on_platform_report(self, report: PlatformReport) -> None:
        """선박 위치 보고 수신."""
        if not self._zones:
            await self.load_zones()
        if not self._zones:
            return

        platform_id = report.platform_id
        point = Point(report.lon, report.lat)

        for zone in self._zones:
            if zone.get("zone_type") not in _ALERT_TYPES:
                continue
            if not zone.get("active", True):
                continue

            zone_id = zone.get("zone_id")
            if not zone_id:
                continue

            geometry = self._zone_shapes.get(zone_id)
            if geometry is None:
                continue

            inside = geometry.contains(point)
            prev_inside = zone_id in self._inside.get(platform_id, set())

            if inside and not prev_inside:
                self._inside.setdefault(platform_id, set()).add(zone_id)
                await self._save_state()
                await self._emit_zone_event(
                    report,
                    zone,
                    event_type="intrusion",
                    severity="critical" if zone["zone_type"] == "prohibited" else "warning",
                )
            elif not inside and prev_inside:
                self._inside.get(platform_id, set()).discard(zone_id)
                if not self._inside.get(platform_id):
                    self._inside.pop(platform_id, None)
                await self._save_state()
                await self._emit_zone_event(
                    report,
                    zone,
                    event_type="exit",
                    severity="info",
                )

    async def _emit_zone_event(
        self,
        report: PlatformReport,
        zone: dict,
        event_type: str,
        severity: str,
    ) -> None:
        payload = {
            "platform_id": report.platform_id,
            "platform_name": report.name or report.platform_id,
            "zone_id": zone.get("zone_id"),
            "zone_name": zone.get("name", "Unknown"),
            "zone_type": zone.get("zone_type"),
            "latitude": report.lat,
            "longitude": report.lon,
            "timestamp": report.timestamp.isoformat(),
            "event_type": event_type,
            "severity": severity,
        }

        await self.emit_event(
            event_type=EventType.DETECT_ZONE,
            payload=payload,
            flow_id=f"detect-zone:{report.platform_id}:{zone.get('zone_id')}:{event_type}",
        )
