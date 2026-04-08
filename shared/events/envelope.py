from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def build_event(
    event_type: str,
    source_service: str,
    *,
    channel: str | None = None,
    produced_at: str | None = None,
) -> dict:
    return {
        "event_id": str(uuid4()),
        "event_type": event_type,
        "produced_at": produced_at or datetime.now(timezone.utc).isoformat(),
        "source_service": source_service,
        "channel": channel,
    }
