"""
Heartbeat Monitor: Device 건강 상태 모니터링 (Server 측)

Device들로부터 정기적으로 수신되는 heartbeat를 추적하여:
1. Offline Device 감지: 30초 이상 heartbeat 없으면 offline 표시
2. 자동 재할당: Middle Agent offline 시, 자식 devices를 다른 parent로 자동 재할당

Moth WebSocket을 통해 device.heartbeat.{device_id} topic을 수신합니다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


class HeartbeatMonitor:
    """
    Device Heartbeat 모니터: 장애 감지 및 자동 복구

    주요 기능:
    1. 주기적 heartbeat 확인: 설정된 interval마다 모든 device 상태 검사
    2. Timeout 감지: timeout 기간 동안 heartbeat 미수신 device를 offline으로 표시
    3. 자동 재할당: Middle layer agent offline 시, 자식들을 새로운 parent로 자동 재할당

    Config:
    - HEARTBEAT_INTERVAL_SECONDS: 모니터링 체크 주기 (기본 10초)
    - HEARTBEAT_TIMEOUT_SECONDS: Offline 판정 timeout (기본 30초)
    """

    def __init__(
        self,
        registry: Any,
        interval_seconds: int = 10,
        timeout_seconds: int = 3,
        distance_calculator: Optional[Callable] = None,
    ):
        """
        Heartbeat Monitor 초기화

        Args:
            registry: DeviceRegistry (in-memory dictionary-based)
            interval_seconds: 모니터링 체크 주기 (초, 기본 10초)
            timeout_seconds: Offline 판정 timeout (초, 기본 30초)
            distance_calculator: 거리 계산 함수 (기본: Haversine)
        """
        self.registry = registry
        self.interval_seconds = interval_seconds  # 모니터링 체크 주기
        self.timeout_seconds = timeout_seconds  # Offline timeout
        self.distance_calculator = distance_calculator or self._default_distance
        self.is_running = False

    def _default_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Haversine 공식으로 두 위치 간 거리 계산

        위도/경도로 표현된 두 지점 사이의 대원거리를 계산합니다.
        동적 재연결 판단에 사용됩니다.

        Args:
            lat1, lon1: 지점 1 (위도, 경도, 도 단위)
            lat2, lon2: 지점 2 (위도, 경도, 도 단위)

        Returns:
            float: 거리 (미터)
        """
        from math import radians, cos, sin, asin, sqrt

        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371000  # Radius of earth in meters
        return c * r

    async def start(self) -> None:
        """Start the heartbeat monitoring loop"""
        self.is_running = True
        logger.info(f"HeartbeatMonitor started: interval={self.interval_seconds}s, timeout={self.timeout_seconds}s")
        await self._monitor_loop()

    async def stop(self) -> None:
        """Stop the monitoring loop"""
        self.is_running = False
        logger.info("HeartbeatMonitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop"""
        while self.is_running:
            try:
                await asyncio.sleep(self.interval_seconds)
                await self._check_all_devices()
            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")

    async def _check_all_devices(self) -> None:
        """Check all devices for timeout"""
        try:
            timeout_threshold = datetime.now(timezone.utc) - timedelta(seconds=self.timeout_seconds)

            # Check all devices in registry
            for device in list(self.registry.list_devices()):
                if device.connected and device.agent.last_seen_at:
                    last_seen = datetime.fromisoformat(device.agent.last_seen_at.replace("Z", "+00:00"))
                    if last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=timezone.utc)
                    if last_seen < timeout_threshold:
                        logger.warning(f"Device {device.id} ({device.name}) marked as offline (no heartbeat)")
                        device.connected = False
                        device.agent.connected = False
                        device.last_error = f"Heartbeat timeout at {datetime.utcnow().isoformat()}"

                        # If middle layer agent goes offline, reassign its children
                        if device.layer == "middle":
                            await self._reassign_children(device)

        except Exception as e:
            logger.error(f"Error checking devices: {e}")

    async def _reassign_children(self, offline_parent: Any) -> None:
        """
        When a middle layer agent goes offline, reassign its children to another parent
        """
        try:
            logger.info(f"Reassigning children of offline parent {offline_parent.id}")

            # Find children with this parent
            children = [
                d for d in self.registry.list_devices()
                if d.parent_id == offline_parent.id
            ]

            for child in children:
                # Find new best parent
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
                    child.updated_at = datetime.utcnow().isoformat()

        except Exception as e:
            logger.error(f"Error reassigning children: {e}")

    def _find_best_parent(
        self,
        latitude: Optional[float],
        longitude: Optional[float],
        exclude_id: Optional[int] = None,
    ) -> Optional[Any]:
        """
        Find the closest available middle layer agent
        """
        if latitude is None or longitude is None:
            return None

        try:
            # Find all online middle layer agents
            candidates = [
                d for d in self.registry.list_devices()
                if d.layer == "middle" and d.connected and d.id != exclude_id
            ]

            if not candidates:
                logger.warning("No available middle layer parents found")
                return None

            # Calculate distances to all candidates
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

            # Return parent with minimum distance
            best_id = min(distances.keys(), key=lambda k: distances[k][1])
            best_parent, best_dist = distances[best_id]
            logger.info(f"Found best parent {best_parent.id} at distance {best_dist:.1f}m")
            return best_parent

        except Exception as e:
            logger.error(f"Error finding best parent: {e}")
            return None

    def record_heartbeat(self, device_id: int, status: str = "online") -> None:
        """
        Record that a device sent a heartbeat (update last_seen_at)
        상태 변경 시에만 DB에 반영 (online ↔ offline)

        Args:
            device_id: Device ID
            status: "online" or "offline"
        """
        try:
            device = self.registry.get_device(device_id)
            if device:
                current_status = "online" if device.connected else "offline"
                new_status = "online" if status == "online" else "offline"

                # Update last_seen_at (always)
                device.agent.last_seen_at = datetime.now(timezone.utc).isoformat()

                # Update connected flag only if status changed
                if current_status != new_status:
                    device.connected = (new_status == "online")
                    device.agent.connected = device.connected
                    device.updated_at = datetime.now(timezone.utc).isoformat()
                    logger.info(f"Device {device_id} status changed: {current_status} → {new_status}")
                else:
                    # Just update last_seen_at, don't change updated_at
                    logger.debug(f"Heartbeat recorded for device {device_id} (status unchanged)")
        except Exception as e:
            logger.error(f"Error recording heartbeat: {e}")
