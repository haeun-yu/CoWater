"""
Healthcheck Monitor: Device 건강 상태 모니터링 (Server 측)

Device들로부터 정기적으로 수신되는 healthcheck를 추적하여:
1. Offline Device 감지: 30초 이상 healthcheck 없으면 offline 표시
2. 자동 재할당: Middle Agent offline 시, 자식 devices를 다른 parent로 자동 재할당

Moth WebSocket을 통해 device.healthcheck topic을 수신합니다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


class HealthcheckMonitor:
    """
    Device Healthcheck 모니터: 장애 감지 및 자동 복구

    주요 기능:
    1. 주기적 healthcheck 확인: 설정된 interval마다 모든 device 상태 검사
    2. Timeout 감지: timeout 기간 동안 healthcheck 미수신 device를 offline으로 표시
    3. 자동 재할당: Middle layer agent offline 시, 자식들을 새로운 parent로 자동 재할당

    Config:
    - HEALTHCHECK_INTERVAL_SECONDS: 모니터링 체크 주기 (기본 10초)
    - HEALTHCHECK_TIMEOUT_SECONDS: Offline 판정 timeout (기본 30초)
    """

    def __init__(
        self,
        registry: Any,
        interval_seconds: int = 10,
        timeout_seconds: int = 3,
        distance_calculator: Optional[Callable] = None,
    ):
        self.registry = registry
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.distance_calculator = distance_calculator or self._default_distance
        self.is_running = False

    def _default_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        from math import radians, cos, sin, asin, sqrt

        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371000
        return c * r

    async def start(self) -> None:
        self.is_running = True
        logger.info(f"HealthcheckMonitor started: interval={self.interval_seconds}s, timeout={self.timeout_seconds}s")
        await self._monitor_loop()

    async def stop(self) -> None:
        self.is_running = False
        logger.info("HealthcheckMonitor stopped")

    async def _monitor_loop(self) -> None:
        while self.is_running:
            try:
                await asyncio.sleep(self.interval_seconds)
                await self._check_all_devices()
            except Exception as e:
                logger.error(f"Error in healthcheck monitor: {e}")

    async def _check_all_devices(self) -> None:
        try:
            timeout_threshold = datetime.now(timezone.utc) - timedelta(seconds=self.timeout_seconds)

            for device in list(self.registry.list_devices()):
                if device.connected and device.agent.last_seen_at:
                    last_seen = datetime.fromisoformat(device.agent.last_seen_at.replace("Z", "+00:00"))
                    if last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=timezone.utc)
                    if last_seen < timeout_threshold:
                        logger.warning(f"Device {device.id} ({device.name}) marked as offline (no healthcheck)")
                        device.connected = False
                        device.agent.connected = False
                        device.last_error = f"Healthcheck timeout at {datetime.now(timezone.utc).isoformat()}"
                        device.updated_at = datetime.now(timezone.utc).isoformat()
                        self.registry._persist_device(device)

                        if device.layer == "middle":
                            await self._reassign_children(device)

        except Exception as e:
            logger.error(f"Error checking devices: {e}")

    async def _reassign_children(self, offline_parent: Any) -> None:
        try:
            logger.info(f"Reassigning children of offline parent {offline_parent.id}")

            children = [
                d for d in self.registry.list_devices()
                if d.parent_id == offline_parent.id
            ]

            for child in children:
                new_parent = self._find_best_parent(
                    child.latitude,
                    child.longitude,
                    exclude_id=offline_parent.id,
                )

                if new_parent:
                    logger.info(
                        f"Reassigning child {child.id} ({child.name}) from parent {offline_parent.id} to {new_parent.id}"
                    )
                    child.parent_id = new_parent.id
                    child.updated_at = datetime.now(timezone.utc).isoformat()
                else:
                    logger.warning(
                        f"No available parent for child {child.id} ({child.name}). "
                        f"Switching to direct_to_system mode."
                    )
                    child.parent_id = None
                    child.updated_at = datetime.now(timezone.utc).isoformat()

                self.registry._persist_device(child)
                await self._notify_child_assignment(child)

        except Exception as e:
            logger.error(f"Error reassigning children: {e}")

    async def _notify_child_assignment(self, child: Any) -> None:
        try:
            if not child.agent or not child.agent.endpoint:
                return

            parent = self.registry._devices.get(child.parent_id) if child.parent_id else None
            route_mode = "via_parent" if parent else "direct_to_system"

            assignment = {
                "message_type": "layer.assignment",
                "device_id": child.id,
                "device_name": child.name,
                "device_type": child.device_type,
                "layer": child.layer,
                "route_mode": route_mode,
                "parent_id": parent.id if parent else None,
                "parent_name": parent.name if parent else None,
                "parent_endpoint": parent.agent.endpoint if parent else None,
                "parent_command_endpoint": parent.agent.command_endpoint if parent else None,
                "force_parent_routing": child.force_parent_routing,
                "a2a": {
                    "endpoint": child.agent.endpoint,
                    "command_endpoint": child.agent.command_endpoint,
                },
            }

            import urllib.request
            import json

            body = {
                "message": {
                    "role": "server",
                    "parts": [{"type": "data", "data": assignment}],
                },
                "metadata": {"source": "device-registration-server", "reason": "middle_parent_offline"},
            }

            req = urllib.request.Request(
                f"{str(child.agent.endpoint).rstrip('/')}/message:send",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=0.5).close()
            logger.info(f"A2A assignment notification sent to child {child.id}")

        except Exception as e:
            logger.debug(f"Failed to send assignment notification to {child.id}: {e}")

    def _find_best_parent(
        self,
        latitude: Optional[float],
        longitude: Optional[float],
        exclude_id: Optional[int] = None,
    ) -> Optional[Any]:
        if latitude is None or longitude is None:
            return None

        try:
            candidates = [
                d for d in self.registry.list_devices()
                if d.layer == "middle" and d.connected and d.id != exclude_id
            ]

            if not candidates:
                logger.warning("No available middle layer parents found")
                return None

            distances = {}
            for parent in candidates:
                if parent.latitude is not None and parent.longitude is not None:
                    dist = self.distance_calculator(
                        latitude,
                        longitude,
                        parent.latitude,
                        parent.longitude,
                    )
                    distances[parent.id] = (parent, dist)

            if not distances:
                logger.warning("Could not calculate distances to any parents")
                return None

            best_id = min(distances.keys(), key=lambda k: distances[k][1])
            best_parent, best_dist = distances[best_id]
            logger.info(f"Found best parent {best_parent.id} at distance {best_dist:.1f}m")
            return best_parent

        except Exception as e:
            logger.error(f"Error finding best parent: {e}")
            return None

    def record_healthcheck(
        self,
        device_id: int,
        status: str = "online",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        battery_percent: Optional[float] = None,
    ) -> None:
        try:
            device = self.registry.get_device(device_id)
            if device:
                current_status = "online" if device.connected else "offline"
                new_status = "online" if status == "online" else "offline"
                battery_changed = False
                location_changed = False

                device.agent.last_seen_at = datetime.now(timezone.utc).isoformat()

                if latitude is not None and longitude is not None:
                    if device.latitude != latitude or device.longitude != longitude:
                        device.latitude = latitude
                        device.longitude = longitude
                        device.last_location_update = datetime.now(timezone.utc).isoformat()
                        location_changed = True

                if battery_percent is not None and device.last_battery_percent != battery_percent:
                    device.last_battery_percent = battery_percent
                    device.last_battery_update = datetime.now(timezone.utc).isoformat()
                    battery_changed = True

                if current_status != new_status or location_changed or battery_changed:
                    device.connected = (new_status == "online")
                    device.agent.connected = device.connected
                    device.updated_at = datetime.now(timezone.utc).isoformat()
                    self.registry._persist_device(device)
                    if current_status != new_status:
                        logger.info(f"Device {device_id} status changed: {current_status} → {new_status}")
                else:
                    logger.debug(f"Healthcheck recorded for device {device_id} (status unchanged)")
        except Exception as e:
            logger.error(f"Error recording healthcheck: {e}")
