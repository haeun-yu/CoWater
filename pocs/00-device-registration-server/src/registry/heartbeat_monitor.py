from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


class HeartbeatMonitor:
    """
    Monitors device heartbeats and marks devices as offline if no heartbeat received.
    Also handles re-assigning children when a middle layer agent goes offline.
    """

    def __init__(
        self,
        db_session: Any,
        interval_seconds: int = 10,
        timeout_seconds: int = 30,
        distance_calculator: Optional[Callable] = None,
    ):
        self.db_session = db_session
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.distance_calculator = distance_calculator or self._default_distance
        self.is_running = False

    def _default_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Simple distance calculation (Haversine formula)
        Returns distance in meters
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
        from sqlalchemy import and_

        try:
            # Import here to avoid circular imports
            from src.registry.device_registry import DeviceRegistry

            timeout_threshold = datetime.utcnow() - timedelta(seconds=self.timeout_seconds)

            # Find offline devices (not seen recently)
            offline_devices = (
                self.db_session.query(DeviceRegistry)
                .filter(
                    and_(
                        DeviceRegistry.last_seen_at < timeout_threshold,
                        DeviceRegistry.connected == True,
                    )
                )
                .all()
            )

            for device in offline_devices:
                logger.warning(f"Device {device.id} ({device.name}) marked as offline (no heartbeat)")
                device.connected = False
                device.last_error = f"Heartbeat timeout at {datetime.utcnow().isoformat()}"
                self.db_session.commit()

                # If middle layer agent goes offline, reassign its children
                if device.layer == "middle":
                    await self._reassign_children(device)

        except Exception as e:
            logger.error(f"Error checking devices: {e}")

    async def _reassign_children(self, offline_parent: Any) -> None:
        """
        When a middle layer agent goes offline, reassign its children to another parent
        """
        from src.registry.device_registry import DeviceRegistry, HierarchyAssignment

        try:
            logger.info(f"Reassigning children of offline parent {offline_parent.id}")

            children = (
                self.db_session.query(DeviceRegistry)
                .filter(DeviceRegistry.parent_id == offline_parent.id)
                .all()
            )

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

                    # Record hierarchy change
                    assignment = HierarchyAssignment(
                        child_id=child.id,
                        parent_id=new_parent.id,
                        assigned_at=datetime.utcnow().isoformat(),
                        reason="parent_offline_reassignment",
                    )
                    self.db_session.add(assignment)

            self.db_session.commit()
        except Exception as e:
            logger.error(f"Error reassigning children: {e}")
            self.db_session.rollback()

    def _find_best_parent(
        self,
        latitude: Optional[float],
        longitude: Optional[float],
        exclude_id: Optional[int] = None,
    ) -> Optional[Any]:
        """
        Find the closest available middle layer agent
        """
        from src.registry.device_registry import DeviceRegistry

        if latitude is None or longitude is None:
            return None

        try:
            # Query all online middle layer agents
            candidates = (
                self.db_session.query(DeviceRegistry)
                .filter(
                    and_(
                        DeviceRegistry.layer == "middle",
                        DeviceRegistry.connected == True,
                        DeviceRegistry.id != exclude_id,
                    )
                )
                .all()
            )

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

    def record_heartbeat(self, device_id: int) -> None:
        """
        Record that a device sent a heartbeat (update last_seen_at)
        Called when device sends heartbeat via HTTP or Moth
        """
        from src.registry.device_registry import DeviceRegistry

        try:
            device = self.db_session.query(DeviceRegistry).filter(DeviceRegistry.id == device_id).first()
            if device:
                device.last_seen_at = datetime.utcnow().isoformat()
                device.connected = True
                self.db_session.commit()
                logger.debug(f"Heartbeat recorded for device {device_id}")
        except Exception as e:
            logger.error(f"Error recording heartbeat: {e}")
