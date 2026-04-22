"""CoWater device stream JSON adapter."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from adapters.base import ParsedReport, ParsedStreamMessage, ProtocolAdapter

logger = logging.getLogger(__name__)

_SUPPORTED_MIME = {
    "application/json",
    "application/vnd.cowater.device-stream+json",
}


class DeviceStreamAdapter(ProtocolAdapter):
    """Parse normalized CoWater device stream messages from Moth."""

    name = "DeviceStreamAdapter"

    def supports_mime(self, mime: str) -> bool:
        base = mime.split(";")[0].strip().lower()
        return base in _SUPPORTED_MIME

    def parse(self, raw: bytes, mime: str) -> ParsedReport | None:
        return None

    def parse_streams(self, raw: bytes, mime: str) -> list[ParsedStreamMessage]:
        if not self.supports_mime(mime):
            return []

        try:
            data = json.loads(raw.decode("utf-8"))
            messages = data if isinstance(data, list) else [data]
            parsed: list[ParsedStreamMessage] = []
            for item in messages:
                parsed_message = self._parse_one(item)
                if parsed_message is not None:
                    parsed.append(parsed_message)
            return parsed
        except Exception:
            logger.exception("DeviceStreamAdapter parse error")
            return []

    def _parse_one(self, data: dict) -> ParsedStreamMessage | None:
        envelope = data.get("envelope") or {}
        payload = data.get("payload") or {}
        stream = envelope.get("stream")
        device_id = envelope.get("device_id")
        if not stream or not device_id:
            logger.warning("Device stream missing stream or device_id")
            return None

        timestamp_raw = envelope.get("timestamp")
        try:
            timestamp = (
                datetime.fromisoformat(timestamp_raw)
                if timestamp_raw
                else datetime.now(timezone.utc)
            )
        except ValueError:
            timestamp = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            timestamp = timestamp.astimezone(timezone.utc)

        return ParsedStreamMessage(
            stream=str(stream),
            device_id=str(device_id),
            device_type=str(envelope.get("device_type", "unknown")),
            timestamp=timestamp,
            payload=dict(payload),
            source=str(envelope.get("source", "unknown")),
            qos=str(envelope.get("qos", "best_effort")),
            parent_device_id=envelope.get("parent_device_id"),
            flow_id=envelope.get("flow_id"),
            causation_id=envelope.get("causation_id"),
            message_id=envelope.get("message_id"),
            schema_version=int(envelope.get("schema_version", 1)),
        )
