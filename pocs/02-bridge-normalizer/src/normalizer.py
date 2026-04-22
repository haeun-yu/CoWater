from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPO_ROOT / "packages" / "schemas"
sys.path.insert(0, str(SCHEMA_ROOT))

from schemas import Device, DeviceStreamMessage  # noqa: E402


def normalize(protocol: str, raw: dict[str, Any]) -> list[DeviceStreamMessage]:
    if protocol == "ros-navsat":
        return normalize_ros_navsat(raw)
    if protocol == "custom-device-stream":
        return normalize_custom_device_stream(raw)
    if protocol == "nmea-ais":
        return normalize_nmea_ais(raw)
    raise ValueError(f"Unsupported protocol: {protocol}")


def normalize_ros_navsat(raw: dict[str, Any]) -> list[DeviceStreamMessage]:
    device = Device(
        device_id=str(raw.get("platform_id") or raw.get("device_id") or "ros-unknown"),
        device_type=str(raw.get("device_type") or "auv"),
        name=str(raw.get("name") or raw.get("platform_id") or "ROS Device"),
        parent_device_id=raw.get("parent_device_id"),
        capabilities=["position"],
        streams=["telemetry.position"],
    )
    payload = {
        "lat": float(raw["latitude"]),
        "lon": float(raw["longitude"]),
        "altitude_m": raw.get("altitude"),
        "heading": raw.get("heading"),
        "source_protocol": "ros",
    }
    return [
        DeviceStreamMessage.build(
            stream="telemetry.position",
            device=device,
            payload=payload,
            source="poc-bridge-normalizer",
            qos="latest",
        )
    ]


def normalize_custom_device_stream(raw: dict[str, Any]) -> list[DeviceStreamMessage]:
    envelope = raw.get("envelope") or {}
    payload = raw.get("payload") or {}
    stream = raw.get("stream") or envelope.get("stream")
    device_id = envelope.get("device_id") or raw.get("device_id")
    if not stream or not device_id:
        raise ValueError("custom-device-stream requires stream and device_id")

    device = Device(
        device_id=str(device_id),
        device_type=str(envelope.get("device_type") or raw.get("device_type") or "vessel"),
        name=str(raw.get("name") or device_id),
        parent_device_id=envelope.get("parent_device_id") or raw.get("parent_device_id"),
        capabilities=[stream.split(".")[-1]],
        streams=[stream],
    )
    return [
        DeviceStreamMessage.build(
            stream=str(stream),
            device=device,
            payload=dict(payload),
            source="poc-bridge-normalizer",
            qos=str(envelope.get("qos") or "best_effort"),
        )
    ]


def normalize_nmea_ais(raw: dict[str, Any]) -> list[DeviceStreamMessage]:
    """Minimal fixture-level AIS normalizer.

    This PoC intentionally avoids pyais. It accepts already decoded AIS-like JSON
    so the boundary can be tested without protocol dependencies.
    """

    device_id = str(raw.get("mmsi") or raw.get("device_id") or "ais-unknown")
    if not device_id.startswith("MMSI-"):
        device_id = f"MMSI-{device_id}"
    device = Device(
        device_id=device_id,
        device_type="vessel",
        name=str(raw.get("name") or device_id),
        capabilities=["position"],
        streams=["telemetry.position"],
    )
    payload = {
        "lat": float(raw["lat"]),
        "lon": float(raw["lon"]),
        "sog": raw.get("sog"),
        "cog": raw.get("cog"),
        "heading": raw.get("heading"),
        "source_protocol": "ais",
    }
    return [
        DeviceStreamMessage.build(
            stream="telemetry.position",
            device=device,
            payload=payload,
            source="poc-bridge-normalizer",
            qos="latest",
        )
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--format", choices=["jsonl", "summary"], default="jsonl")
    args = parser.parse_args()

    raw = json.loads(Path(args.input).read_text())
    messages = normalize(args.protocol, raw)
    lines = (
        render_summary(args.protocol, raw, messages)
        if args.format == "summary"
        else [json.dumps(message.to_dict(), separators=(",", ":")) for message in messages]
    )

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))


def render_summary(
    protocol: str,
    raw: dict[str, Any],
    messages: list[DeviceStreamMessage],
) -> list[str]:
    rows = [
        "BRIDGE NORMALIZER",
        f"protocol: {protocol}",
        f"input keys: {', '.join(sorted(raw.keys()))}",
        "",
        f"{'subject':<34} {'stream':<20} {'qos':<10} payload",
        "-" * 90,
    ]
    for message in messages:
        rows.append(
            f"{message.envelope.subject:<34} {message.stream:<20} {message.envelope.qos:<10} "
            f"{', '.join(sorted(message.payload.keys()))}"
        )
    return rows


if __name__ == "__main__":
    main()
