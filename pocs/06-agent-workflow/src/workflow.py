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

from schemas import AgentEvent, Alert, Envelope  # noqa: E402


def load_events(path: Path) -> list[dict[str, Any]]:
    text = path.read_text().strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def handle_detect_mine(event: dict[str, Any]) -> list[dict[str, Any]]:
    envelope = event.get("envelope") or {}
    payload = event.get("payload") or {}
    event_type = event.get("event_type")
    if event_type != "detect.mine":
        return []

    flow_id = envelope.get("flow_id") or str(uuid4())
    device_id = envelope.get("device_id") or payload.get("device_id")
    confidence = float(payload.get("confidence") or 0.0)
    severity = "critical" if confidence >= 0.75 else "warning"

    analysis = AgentEvent(
        envelope=Envelope(
            subject=f"analyze.mine.{flow_id}",
            source="poc-agent-workflow",
            device_id=device_id,
            device_type=envelope.get("device_type"),
            parent_device_id=envelope.get("parent_device_id"),
            flow_id=flow_id,
            causation_id=envelope.get("message_id"),
            qos="durable",
        ),
        event_type="analyze.mine",
        agent_id="mine-analysis-agent",
        payload={
            "device_id": device_id,
            "contact_id": payload.get("contact_id"),
            "risk": severity,
            "confidence": confidence,
            "recommendation": "Request operator approval for ROV inspection.",
        },
    )

    alert = Alert(
        alert_id=str(uuid4()),
        alert_type="mine_detected",
        severity=severity,
        status="new",
        device_ids=[device_id] if device_id else [],
        message=(
            f"Mine-like sonar contact detected by {device_id} "
            f"confidence={confidence:.2f}"
        ),
        metadata={
            "flow_id": flow_id,
            "contact_id": payload.get("contact_id"),
            "recommendation": "Request operator approval for ROV inspection.",
        },
    )

    return [
        {"kind": "agent_event", **analysis.to_dict()},
        {"kind": "alert", **alert.to_dict()},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    rows: list[str] = []
    for event in load_events(Path(args.input)):
        rows.extend(json.dumps(item, separators=(",", ":")) for item in handle_detect_mine(event))
    print("\n".join(rows))


if __name__ == "__main__":
    main()
