"""
Zone Monitor Agent — 금지구역/제한구역 침입 감지.

Core API에서 Zone 목록을 주기적으로 로드하고,
각 선박 위치가 Zone Geometry 내에 있는지 확인.

Shapely를 사용하여 폴리곤 홀(hole)을 포함한 정확한 공간 연산을 수행한다.
"""

from __future__ import annotations

import json
import logging

import httpx
import redis.asyncio as aioredis
from shapely.geometry import Point, shape

from base import Agent, AlertPayload, PlatformReport

logger = logging.getLogger(__name__)

_ALERT_TYPES = {"prohibited", "restricted"}   # 경보 발생 구역 유형
_STATE_KEY = "agent:zone_monitor:inside"
_STATE_TTL = 3600


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

    async def restore_state(self) -> None:
        """서비스 시작 시 Redis에서 구역 내부 상태 복구."""
        try:
            raw = await self._redis.get(_STATE_KEY)
            if not raw:
                return
            data = json.loads(raw)
            self._inside = {pid: set(zone_ids) for pid, zone_ids in data.items()}
            logger.info("ZoneMonitorAgent state restored: %d platforms inside zones", len(self._inside))
        except Exception:
            logger.exception("Failed to restore ZoneMonitorAgent state")

    async def _save_state(self) -> None:
        try:
            data = {pid: list(zone_ids) for pid, zone_ids in self._inside.items() if zone_ids}
            await self._redis.set(_STATE_KEY, json.dumps(data), ex=_STATE_TTL)
        except Exception:
            logger.warning("Failed to save ZoneMonitorAgent state")

    async def load_zones(self) -> None:
        """Core API에서 활성 Zone 목록 로드 및 Shapely geometry 파싱."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._core_api_url}/zones", timeout=5)
                resp.raise_for_status()
                self._zones = resp.json()
                self._zone_shapes = {}
                valid_zone_ids = set()
                for zone in self._zones:
                    zone_id = zone["zone_id"]
                    valid_zone_ids.add(zone_id)
                    try:
                        self._zone_shapes[zone_id] = shape(zone["geometry"])
                    except Exception:
                        logger.warning("Failed to parse geometry for zone %s", zone_id)

                # 삭제되거나 비활성화된 zone에 대한 _inside 상태 정리
                for platform_id in list(self._inside.keys()):
                    invalid_zones = self._inside[platform_id] - valid_zone_ids
                    if invalid_zones:
                        self._inside[platform_id] -= invalid_zones
                        if not self._inside[platform_id]:
                            del self._inside[platform_id]

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
                await self._save_state()
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
                await self._save_state()
                await self.emit_alert(AlertPayload(
                    alert_type="zone_exit",
                    severity="info",
                    message=f"{report.platform_id}가 구역 '{zone['name']}'에서 이탈",
                    platform_ids=[report.platform_id],
                    zone_id=zone_id,
                    dedup_key=f"zone_exit:{report.platform_id}:{zone_id}",
                    resolve_dedup_key=f"zone:{report.platform_id}:{zone_id}",
                ))
