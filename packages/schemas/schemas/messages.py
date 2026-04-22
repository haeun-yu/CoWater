from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


QoS = Literal["latest", "best_effort", "sampled", "durable"]
DeviceType = Literal["control_usv", "small_usv", "auv", "rov", "vessel", "buoy"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Envelope:
    message_id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = 1
    subject: str = ""
    timestamp: str = field(default_factory=utc_now_iso)
    source: str = "unknown"
    device_id: str | None = None
    device_type: str | None = None
    parent_device_id: str | None = None
    flow_id: str | None = None
    causation_id: str | None = None
    qos: QoS = "best_effort"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Device:
    device_id: str
    device_type: DeviceType
    name: str
    parent_device_id: str | None = None
    mission_id: str | None = None
    capabilities: list[str] = field(default_factory=list)
    streams: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceStreamMessage:
    envelope: Envelope
    stream: str
    payload: dict[str, Any]

    @classmethod
    def build(
        cls,
        *,
        stream: str,
        device: Device,
        payload: dict[str, Any],
        source: str,
        qos: QoS,
    ) -> "DeviceStreamMessage":
        return cls(
            envelope=Envelope(
                subject=f"{stream}.{device.device_id}",
                source=source,
                device_id=device.device_id,
                device_type=device.device_type,
                parent_device_id=device.parent_device_id,
                qos=qos,
            ),
            stream=stream,
            payload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_dict(),
            "stream": self.stream,
            "payload": self.payload,
        }


@dataclass
class DomainEvent:
    envelope: Envelope
    event_type: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_dict(),
            "event_type": self.event_type,
            "payload": self.payload,
        }


@dataclass
class AgentEvent:
    envelope: Envelope
    event_type: str
    agent_id: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_dict(),
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "payload": self.payload,
        }


@dataclass
class Alert:
    alert_id: str
    alert_type: str
    severity: Literal["info", "warning", "critical"]
    status: Literal["new", "acknowledged", "resolved"]
    device_ids: list[str]
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StreamPolicy:
    stream: str
    qos: QoS
    retention: str
    persist: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
