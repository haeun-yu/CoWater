from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPO_ROOT / "packages" / "schemas"
sys.path.insert(0, str(SCHEMA_ROOT))

from schemas import DomainEvent, Envelope  # noqa: E402


def load_messages(path: Path) -> list[dict[str, Any]]:
    text = path.read_text().strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def detect_mines(message: dict[str, Any], threshold: float) -> list[DomainEvent]:
    stream = message.get("stream")
    if stream != "sensor.sonar":
        return []

    envelope = message.get("envelope") or {}
    payload = message.get("payload") or {}
    device_id = envelope.get("device_id")
    device_type = envelope.get("device_type")
    contacts = payload.get("contacts") or []
    events: list[DomainEvent] = []

    for contact in contacts:
        confidence = float(contact.get("confidence") or 0.0)
        if confidence < threshold:
            continue
        contact_id = str(contact.get("contact_id") or f"{device_id}:{payload.get('ping_id')}")
        flow_id = str(uuid4())
        events.append(
            DomainEvent(
                envelope=Envelope(
                    subject=f"detect.mine.{device_id}",
                    source="poc-detection-agents",
                    device_id=device_id,
                    device_type=device_type,
                    parent_device_id=envelope.get("parent_device_id"),
                    flow_id=flow_id,
                    causation_id=envelope.get("message_id"),
                    qos="durable",
                ),
                event_type="detect.mine",
                payload={
                    "device_id": device_id,
                    "contact_id": contact_id,
                    "classification": contact.get("classification"),
                    "confidence": confidence,
                    "range_m": contact.get("range_m"),
                    "bearing_deg": contact.get("bearing_deg"),
                    "ping_id": payload.get("ping_id"),
                    "severity": "critical" if confidence >= 0.75 else "warning",
                },
            )
        )
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--threshold", type=float, default=0.4)
    args = parser.parse_args()

    output: list[str] = []
    for message in load_messages(Path(args.input)):
        output.extend(
            json.dumps(event.to_dict(), separators=(",", ":"))
            for event in detect_mines(message, args.threshold)
        )
    print("\n".join(output))


if __name__ == "__main__":
    main()
