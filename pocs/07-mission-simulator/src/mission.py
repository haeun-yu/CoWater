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


def run_scenario(path: Path) -> list[DomainEvent]:
    scenario = json.loads(path.read_text())
    mission_id = scenario["mission_id"]
    flow_id = str(uuid4())
    events: list[DomainEvent] = []
    previous_id: str | None = None
    for item in scenario["timeline"]:
        event_type = item["event"]
        device_id = item.get("device_id")
        event = DomainEvent(
            envelope=Envelope(
                subject=f"mission.{event_type}.{device_id or mission_id}",
                source="poc-mission-simulator",
                device_id=device_id,
                flow_id=flow_id,
                causation_id=previous_id,
                qos="durable",
            ),
            event_type=event_type,
            payload={
                "mission_id": mission_id,
                "at_s": item["at_s"],
                "device_id": device_id,
            },
        )
        previous_id = event.envelope.message_id
        events.append(event)
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="scenarios/mine-clearance.json")
    parser.add_argument("--output")
    args = parser.parse_args()

    rows = [json.dumps(event.to_dict(), separators=(",", ":")) for event in run_scenario(Path(args.scenario))]
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(rows) + "\n")
    else:
        print("\n".join(rows))


if __name__ == "__main__":
    main()
