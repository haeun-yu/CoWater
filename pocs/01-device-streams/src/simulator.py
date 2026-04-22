from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPO_ROOT / "packages" / "schemas"
sys.path.insert(0, str(SCHEMA_ROOT))

from schemas import Device, DeviceStreamMessage  # noqa: E402


STREAM_QOS = {
    "telemetry.position": "latest",
    "telemetry.status": "best_effort",
    "telemetry.network": "best_effort",
    "telemetry.task": "best_effort",
    "sensor.sonar": "sampled",
    "device.event": "durable",
}


def load_devices(path: Path) -> list[Device]:
    data = json.loads(path.read_text())
    return [Device(**item) for item in data]


def build_messages(device: Device, tick: int) -> Iterable[DeviceStreamMessage]:
    for stream in device.streams:
        payload = payload_for(device, stream, tick)
        if payload is None:
            continue
        yield DeviceStreamMessage.build(
            stream=stream,
            device=device,
            payload=payload,
            source="poc-device-streams",
            qos=STREAM_QOS.get(stream, "best_effort"),
        )


def payload_for(device: Device, stream: str, tick: int) -> dict | None:
    seed = sum(ord(ch) for ch in device.device_id)
    base_lat = 35.05 + seed % 20 * 0.001
    base_lon = 129.03 + seed % 15 * 0.001
    heading = (tick * 8 + len(device.device_id)) % 360

    if stream == "telemetry.position":
        return {
            "lat": round(base_lat + math.sin(tick / 10) * 0.005, 6),
            "lon": round(base_lon + math.cos(tick / 10) * 0.005, 6),
            "sog": 4.0 if device.device_type != "rov" else 0.8,
            "heading": heading,
        }
    if stream == "telemetry.status":
        return {
            "state": "surveying" if device.device_type == "auv" else "ready",
            "battery_pct": max(20, 100 - tick),
            "health": "nominal",
        }
    if stream == "telemetry.network":
        return {
            "connected": True,
            "latency_ms": 80 + tick % 5 * 15,
            "packet_loss_pct": 0 if tick % 9 else 10,
        }
    if stream == "telemetry.task":
        return {
            "task_id": f"mission-alpha:{device.device_id}",
            "phase": "survey",
            "progress_pct": min(100, tick * 2),
        }
    if stream == "sensor.sonar":
        return {
            "ping_id": f"{device.device_id}:{tick}",
            "contacts": [
                {
                    "contact_id": f"contact-{device.device_id}-mine-like",
                    "classification": "unknown_object",
                    "confidence": 0.42 + (tick % 5) * 0.04,
                    "range_m": 80 + tick % 10,
                    "bearing_deg": (heading + 20) % 360,
                }
            ],
        }
    if stream == "device.event" and tick == 3:
        return {
            "event_type": "rov.ready",
            "message": f"{device.name} is ready for deployment",
        }
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--devices", default="devices.json")
    parser.add_argument("--ticks", type=int, default=5)
    parser.add_argument("--output")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    devices = load_devices(base_dir / args.devices)

    lines: list[str] = []
    for tick in range(args.ticks):
        for device in devices:
            for message in build_messages(device, tick):
                lines.append(json.dumps(message.to_dict(), separators=(",", ":")))

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
