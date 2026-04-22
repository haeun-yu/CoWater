from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_report(events: list[dict[str, Any]], feedback: dict[str, Any] | None) -> dict[str, Any]:
    event_types = [event.get("event_type") or event.get("kind") for event in events]
    flow_ids = sorted(
        {
            (event.get("envelope") or {}).get("flow_id")
            for event in events
            if (event.get("envelope") or {}).get("flow_id")
        }
    )
    suggestion = None
    if feedback and feedback.get("label") == "false_positive":
        suggestion = {
            "parameter": "mine_detection_confidence_threshold",
            "current": 0.4,
            "recommended": 0.55,
            "status": "pending_approval",
        }
    return {
        "title": "Mission Incident Summary",
        "event_count": len(events),
        "event_types": event_types,
        "flow_ids": flow_ids,
        "summary": f"Processed {len(events)} mission/event records.",
        "feedback": feedback,
        "learning_suggestion": suggestion,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--feedback")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()
    feedback = json.loads(Path(args.feedback).read_text()) if args.feedback else None
    report = build_report(load_jsonl(Path(args.events)), feedback)
    if args.format == "markdown":
        print(render_markdown(report))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['title']}",
        "",
        f"- Events processed: {report['event_count']}",
        f"- Flow IDs: {', '.join(report['flow_ids']) if report['flow_ids'] else '-'}",
        f"- Event types: {', '.join(str(t) for t in report['event_types'])}",
        "",
        "## Summary",
        report["summary"],
    ]
    if report.get("feedback"):
        feedback = report["feedback"]
        lines.extend(["", "## Feedback", f"- Label: {feedback.get('label')}", f"- Reason: {feedback.get('reason')}"])
    if report.get("learning_suggestion"):
        suggestion = report["learning_suggestion"]
        lines.extend(
            [
                "",
                "## Learning Suggestion",
                f"- Parameter: `{suggestion['parameter']}`",
                f"- Current: {suggestion['current']}",
                f"- Recommended: {suggestion['recommended']}",
                f"- Status: {suggestion['status']}",
            ]
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
