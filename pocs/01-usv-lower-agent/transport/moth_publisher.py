from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

try:
    import websockets
except ImportError:
    websockets = None

if TYPE_CHECKING:
    from agent.state import AgentState

logger = logging.getLogger(__name__)


class MothPublisher:
    """
    Publishes device telemetry and heartbeats to Moth WebSocket server
    """

    def __init__(self, config: dict[str, Any], state: AgentState):
        self.config = config
        self.state = state
        self.moth_config = config.get("moth", {})
        self.moth_url = self.moth_config.get("server_url", "wss://cobot.center:8287")
        self.enabled = self.moth_config.get("enabled", True)
        self.ws: Optional[Any] = None
        self.is_connected = False

        # Topics assigned by Server during registration
        self.heartbeat_topic: Optional[str] = None
        self.telemetry_topics: dict[str, str] = {}  # {track_type: topic}

    async def initialize(self, registration_response: dict[str, Any]) -> None:
        """
        Initialize topics from server registration response
        """
        if not self.enabled or websockets is None:
            logger.info("MothPublisher disabled or websockets not available")
            return

        self.heartbeat_topic = registration_response.get("heartbeat_topic")
        telemetry_topics_list = registration_response.get("telemetry_topics", [])

        for topic_info in telemetry_topics_list:
            track_type = topic_info.get("track_type")
            topic = topic_info.get("topic")
            if track_type and topic:
                self.telemetry_topics[track_type] = topic

        logger.info(f"MothPublisher initialized with {len(self.telemetry_topics)} telemetry topics")
        logger.debug(f"Heartbeat topic: {self.heartbeat_topic}")

    async def connect(self) -> None:
        """Connect to Moth WebSocket server"""
        if not self.enabled or websockets is None:
            return

        if self.ws is not None and not self.ws.closed:
            return

        try:
            logger.info(f"Connecting to Moth: {self.moth_url}")
            self.ws = await websockets.connect(self.moth_url, ping_interval=30, ping_timeout=10)
            self.is_connected = True
            logger.info("Connected to Moth")
        except Exception as e:
            logger.error(f"Failed to connect to Moth: {e}")
            self.is_connected = False

    async def _reconnect_loop(self) -> None:
        """Auto-reconnect loop"""
        reconnect_interval = self.moth_config.get("reconnect_interval_seconds", 5)

        while True:
            try:
                if not self.is_connected or self.ws is None or self.ws.closed:
                    await self.connect()
                await asyncio.sleep(reconnect_interval)
            except Exception as e:
                logger.debug(f"Reconnect error: {e}")
                await asyncio.sleep(reconnect_interval)

    async def publish_heartbeat(self) -> None:
        """
        Publish device heartbeat periodically
        """
        if not self.heartbeat_topic or not self.is_connected or self.ws is None or self.ws.closed:
            return

        payload = {
            "device_id": self.state.registry_id,
            "agent_id": self.state.agent_id,
            "layer": self.state.layer,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "online" if self.state.connected else "offline",
            "battery_percent": self.state.last_telemetry.get("battery_percent", 100) if self.state.last_telemetry else 100,
        }

        try:
            await self.ws.send(
                json.dumps(
                    {"type": "publish", "topic": self.heartbeat_topic, "payload": payload}
                )
            )
            logger.debug(f"Heartbeat published: {self.heartbeat_topic}")
        except Exception as e:
            logger.error(f"Failed to publish heartbeat: {e}")
            self.is_connected = False

    async def publish_telemetry(self, telemetry: dict[str, Any]) -> None:
        """
        Publish sensor telemetry data for each track type
        """
        if not self.is_connected or self.ws is None or self.ws.closed:
            return

        # GPS/Position data (important for re-binding)
        if self.telemetry_topics.get("GPS") and self.state.latitude is not None:
            try:
                gps_payload = {
                    "device_id": self.state.registry_id,
                    "latitude": self.state.latitude,
                    "longitude": self.state.longitude,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "publish",
                            "topic": self.telemetry_topics["GPS"],
                            "payload": gps_payload,
                        }
                    )
                )
                logger.debug(f"GPS published: {self.state.latitude}, {self.state.longitude}")
            except Exception as e:
                logger.debug(f"Failed to publish GPS: {e}")

        # Battery data
        if self.telemetry_topics.get("BATTERY") and "battery_percent" in telemetry:
            try:
                battery_payload = {
                    "device_id": self.state.registry_id,
                    "percent": telemetry["battery_percent"],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "publish",
                            "topic": self.telemetry_topics["BATTERY"],
                            "payload": battery_payload,
                        }
                    )
                )
                logger.debug(f"Battery published: {telemetry['battery_percent']}%")
            except Exception as e:
                logger.debug(f"Failed to publish battery: {e}")

        # Motion/ODOMETRY data
        if self.telemetry_topics.get("ODOMETRY") and "motion" in telemetry:
            try:
                motion_payload = {
                    "device_id": self.state.registry_id,
                    "motion": telemetry["motion"],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "publish",
                            "topic": self.telemetry_topics["ODOMETRY"],
                            "payload": motion_payload,
                        }
                    )
                )
            except Exception as e:
                logger.debug(f"Failed to publish odometry: {e}")

        # Depth/Pressure (for AUV)
        if self.telemetry_topics.get("DEPTH") and "depth" in telemetry:
            try:
                depth_payload = {
                    "device_id": self.state.registry_id,
                    "depth_meters": telemetry["depth"],
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await self.ws.send(
                    json.dumps(
                        {
                            "type": "publish",
                            "topic": self.telemetry_topics["DEPTH"],
                            "payload": depth_payload,
                        }
                    )
                )
            except Exception as e:
                logger.debug(f"Failed to publish depth: {e}")

    async def heartbeat_loop(self) -> None:
        """Periodic heartbeat publishing loop"""
        interval = self.config.get("registry", {}).get("heartbeat_interval_seconds", 10)

        logger.info(f"Starting heartbeat loop: interval={interval}s")

        while True:
            try:
                await asyncio.sleep(interval)
                await self.publish_heartbeat()
            except Exception as e:
                logger.debug(f"Error in heartbeat loop: {e}")
