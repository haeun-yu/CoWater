"""
Zone Monitor Agent — 금지구역/제한구역 침입 감지.

Core API에서 Zone 목록을 주기적으로 로드하고,
각 선박 위치가 Zone Geometry 내에 있는지 확인.

Shapely를 사용하여 폴리곤 홀(hole)을 포함한 정확한 공간 연산을 수행한다.
"""

from __future__ import annotations

import logging

import httpx
import redis.asyncio as aioredis
from shapely.geometry import Point, shape

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
        self._zone_shapes: dict[str, object] = {}   # zone_id → Shapely geometry
        self._inside: dict[str, set[str]] = {}       # platform_id → {zone_id, ...}

    async def load_zones(self) -> None:
        """Core API에서 활성 Zone 목록 로드 및 Shapely geometry 파싱."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._core_api_url}/zones", timeout=5)
                resp.raise_for_status()
                self._zones = resp.json()
                self._zone_shapes = {}
                for zone in self._zones:
                    try:
                        self._zone_shapes[zone["zone_id"]] = shape(zone["geometry"])
                    except Exception:
                        logger.warning("Failed to parse geometry for zone %s", zone.get("zone_id"))
                logger.info("Loaded %d zones", len(self._zones))
        except Exception:
            logger.exception("Failed to load zones")

    async def on_platform_report(self, report: PlatformReport) -> None:
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
                # 이탈 — 침입 경보를 자동 해제
                self._inside.get(report.platform_id, set()).discard(zone_id)
                await self.emit_alert(AlertPayload(
                    alert_type="zone_exit",
                    severity="info",
                    message=f"{report.platform_id}가 구역 '{zone['name']}'에서 이탈",
                    platform_ids=[report.platform_id],
                    zone_id=zone_id,
                    dedup_key=f"zone_exit:{report.platform_id}:{zone_id}",
                    resolve_dedup_key=f"zone:{report.platform_id}:{zone_id}",
                ))
