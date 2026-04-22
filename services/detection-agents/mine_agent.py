"""Sonar-based mine detection agent."""

from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis

from base import DetectionAgent
from shared.events import EventType
from shared.schemas.device_stream import DeviceStreamMessage
from shared.schemas.report import PlatformReport


class DetectionMineAgent(DetectionAgent):
    agent_id = "detection-mine"
    agent_type = "detection"

    def __init__(
        self,
        redis: aioredis.Redis,
        core_api_url: str,
        confidence_threshold: float,
        emit_cooldown_sec: int,
    ) -> None:
        super().__init__(redis, core_api_url)
        self._confidence_threshold = confidence_threshold
        self._emit_cooldown_sec = emit_cooldown_sec
        self._last_emit_by_contact: dict[str, datetime] = {}

    async def on_platform_report(self, report: PlatformReport) -> None:
        return None

    async def on_device_stream(self, message: DeviceStreamMessage) -> None:
        if message.envelope.stream != "sensor.sonar":
            return

        contacts = message.payload.get("contacts")
        if not isinstance(contacts, list):
            return

        for contact in contacts:
            if not isinstance(contact, dict):
                continue
            confidence = float(contact.get("confidence") or 0.0)
            classification = str(contact.get("classification") or "unknown")
            if confidence < self._confidence_threshold:
                continue
            if classification not in {"mine", "suspected_mine", "unknown_object"}:
                continue

            contact_id = str(
                contact.get("contact_id")
                or f"{message.envelope.device_id}:{message.payload.get('ping_id')}"
            )
            if self._is_in_cooldown(contact_id):
                continue
            self._last_emit_by_contact[contact_id] = datetime.now(timezone.utc)

            await self.emit_event(
                event_type=EventType.DETECT_MINE,
                payload={
                    "platform_id": message.envelope.device_id,
                    "platform_name": message.payload.get("name")
                    or message.envelope.device_id,
                    "device_type": message.envelope.device_type,
                    "contact_id": contact_id,
                    "classification": classification,
                    "confidence": confidence,
                    "range_m": contact.get("range_m"),
                    "bearing_deg": contact.get("bearing_deg"),
                    "ping_id": message.payload.get("ping_id"),
                    "timestamp": message.envelope.timestamp,
                    "severity": "warning" if confidence < 0.75 else "critical",
                },
            )

    def _is_in_cooldown(self, contact_id: str) -> bool:
        last_emit = self._last_emit_by_contact.get(contact_id)
        if last_emit is None:
            return False
        age = (datetime.now(timezone.utc) - last_emit).total_seconds()
        return age < self._emit_cooldown_sec
