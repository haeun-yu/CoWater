from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


STREAM_SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StreamEnvelope:
    message_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = STREAM_SCHEMA_VERSION
    stream: str = ""
    timestamp: str = field(default_factory=utc_now_iso)
    source: str = "unknown"
    device_id: str = ""
    device_type: str = "unknown"
    parent_device_id: str | None = None
    flow_id: str | None = None
    causation_id: str | None = None
    qos: str = "best_effort"

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "schema_version": self.schema_version,
            "stream": self.stream,
            "timestamp": self.timestamp,
            "source": self.source,
            "device_id": self.device_id,
            "device_type": self.device_type,
            "parent_device_id": self.parent_device_id,
            "flow_id": self.flow_id,
            "causation_id": self.causation_id,
            "qos": self.qos,
        }


@dataclass
class DeviceStreamMessage:
    envelope: StreamEnvelope
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_dict(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceStreamMessage":
        envelope_data = data.get("envelope") or {}
        return cls(
            envelope=StreamEnvelope(
                message_id=envelope_data.get("message_id") or str(uuid4()),
                schema_version=int(
                    envelope_data.get("schema_version", STREAM_SCHEMA_VERSION)
                ),
                stream=str(envelope_data.get("stream", "")),
                timestamp=str(envelope_data.get("timestamp") or utc_now_iso()),
                source=str(envelope_data.get("source", "unknown")),
                device_id=str(envelope_data.get("device_id", "")),
                device_type=str(envelope_data.get("device_type", "unknown")),
                parent_device_id=envelope_data.get("parent_device_id"),
                flow_id=envelope_data.get("flow_id"),
                causation_id=envelope_data.get("causation_id"),
                qos=str(envelope_data.get("qos", "best_effort")),
            ),
            payload=dict(data.get("payload") or {}),
        )


def stream_subject(stream: str, device_id: str) -> str:
    safe_stream = stream.strip(".")
    return f"{safe_stream}.{device_id}"
