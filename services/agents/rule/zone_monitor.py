"""
Zone Monitor Agent — 금지구역/제한구역 침입 감지.

Core API에서 Zone 목록을 주기적으로 로드하고,
각 선박 위치가 Zone Geometry 내에 있는지 확인.
"""

from __future__ import annotations

import logging
import math

import httpx
import redis.asyncio as aioredis

from base import Agent, AlertPayload, PlatformReport

logger = logging.getLogger(__name__)

_ALERT_TYPES = {"prohibited", "restricted"}   # 경보 발생 구역 유형


class ZoneMonitorAgent(Agent):
    agent_id = "zone-monitor"
    name = "Zone Monitor Agent"
    description = "금지구역 및 제한구역 침입 감지"
    agent_type = "rule"

    def __init__(self, redis: aioredis.Redis, core_api_url: str) -> None:
        super().__init__(redis)
        self._core_api_url = core_api_url
        self._zones: list[dict] = []
        self._inside: dict[str, set[str]] = {}     # platform_id → {zone_id, ...}

    async def load_zones(self) -> None:
        """Core API에서 활성 Zone 목록 로드."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._core_api_url}/zones", timeout=5)
                resp.raise_for_status()
                self._zones = resp.json()
                logger.info("Loaded %d zones", len(self._zones))
        except Exception:
            logger.exception("Failed to load zones")

    async def on_platform_report(self, report: PlatformReport) -> None:
        for zone in self._zones:
            if zone.get("zone_type") not in _ALERT_TYPES:
                continue
            if not zone.get("active", True):
                continue

            inside = _point_in_polygon(report.lat, report.lon, zone["geometry"])
            zone_id = zone["zone_id"]
            prev_inside = zone_id in self._inside.get(report.platform_id, set())

            if inside and not prev_inside:
                # 신규 진입
                self._inside.setdefault(report.platform_id, set()).add(zone_id)
                severity = "critical" if zone["zone_type"] == "prohibited" else "warning"
                rec = None
                if self.level in ("L2", "L3"):
                    rec = f"{zone['name']}에서 즉시 이탈하십시오."
                await self.emit_alert(AlertPayload(
                    alert_type="zone_intrusion",
                    severity=severity,
                    message=f"{report.platform_id}가 {zone['zone_type']} 구역 '{zone['name']}'에 진입",
                    platform_ids=[report.platform_id],
                    zone_id=zone_id,
                    recommendation=rec,
                    dedup_key=f"zone:{report.platform_id}:{zone_id}",
                ))

            elif not inside and prev_inside:
                # 이탈
                self._inside.get(report.platform_id, set()).discard(zone_id)
                await self.emit_alert(AlertPayload(
                    alert_type="zone_intrusion",
                    severity="info",
                    message=f"{report.platform_id}가 구역 '{zone['name']}'에서 이탈",
                    platform_ids=[report.platform_id],
                    zone_id=zone_id,
                ))


def _point_in_polygon(lat: float, lon: float, geometry: dict) -> bool:
    """
    GeoJSON Polygon 내부 여부 판단 (Ray Casting).
    외부 링만 사용 (hole 무시).
    """
    geo_type = geometry.get("type", "")
    coords_list = []

    if geo_type == "Polygon":
        coords_list = [geometry["coordinates"][0]]
    elif geo_type == "MultiPolygon":
        coords_list = [poly[0] for poly in geometry["coordinates"]]
    else:
        return False

    for ring in coords_list:
        if _ray_cast(lon, lat, ring):
            return True
    return False


def _ray_cast(x: float, y: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside
