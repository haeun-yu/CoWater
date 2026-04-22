from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class ContractBus:
    def __init__(self, policies: dict[str, Any]) -> None:
        self._policies = policies
        self.latest: dict[str, dict[str, Any]] = {}
        self.durable: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.best_effort_count = 0

    def publish(self, message: dict[str, Any]) -> None:
        envelope = message.get("envelope") or {}
        subject = envelope.get("subject")
        stream = message.get("stream") or _stream_from_subject(subject)
        device_id = envelope.get("device_id")
        if not subject or not stream:
            raise ValueError("message requires envelope.subject and stream")

        policy = self._policies.get(stream, {})
        qos = policy.get("qos") or envelope.get("qos") or "best_effort"
        if qos == "latest":
            if not device_id:
                raise ValueError(f"latest stream requires device_id: {subject}")
            self.latest[f"{stream}:{device_id}"] = message
        elif qos == "durable":
            self.durable[stream].append(message)
        else:
            self.best_effort_count += 1

    def summary(self) -> dict[str, Any]:
        return {
            "latest_keys": sorted(self.latest),
            "durable_counts": {k: len(v) for k, v in sorted(self.durable.items())},
            "best_effort_count": self.best_effort_count,
        }


def _stream_from_subject(subject: str | None) -> str | None:
    if not subject:
        return None
    parts = subject.split(".")
    if len(parts) < 3:
        return subject
    return ".".join(parts[:-1])


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policies", default="stream-policies.json")
    parser.add_argument("--input", required=True)
    parser.add_argument("--format", choices=["json", "table"], default="json")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    policies = json.loads((base_dir / args.policies).read_text())
    messages = load_jsonl(Path(args.input))
    bus = ContractBus(policies)
    for message in messages:
        bus.publish(message)
    if args.format == "table":
        print("\n".join(render_table(bus.summary(), policies)))
    else:
        print(json.dumps(bus.summary(), indent=2, sort_keys=True))


def render_table(summary: dict[str, Any], policies: dict[str, Any]) -> list[str]:
    rows = [
        "EVENT BUS CONTRACT",
        f"{'stream':<22} {'qos':<12} {'result'}",
        "-" * 62,
    ]
    latest_by_stream: dict[str, int] = defaultdict(int)
    for key in summary["latest_keys"]:
        stream, _device_id = key.split(":", 1)
        latest_by_stream[stream] += 1
    for stream, policy in sorted(policies.items()):
        qos = policy.get("qos", "best_effort")
        if qos == "latest":
            result = f"{latest_by_stream.get(stream, 0)} latest device keys"
        elif qos == "durable":
            result = f"{summary['durable_counts'].get(stream, 0)} durable events"
        else:
            result = "best-effort traffic"
        rows.append(f"{stream:<22} {qos:<12} {result}")
    rows.append("")
    rows.append(f"best_effort_count={summary['best_effort_count']}")
    return rows


if __name__ == "__main__":
    main()
