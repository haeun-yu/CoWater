from __future__ import annotations

from typing import Dict, List
from uuid import uuid4

from src.core.models import EventIngestRequest, EventRecord


class EventRegistry:
    def __init__(self) -> None:
        self._events: Dict[str, EventRecord] = {}

    def ingest_event(self, request: EventIngestRequest) -> EventRecord:
        event_id = request.event_id or f"event-{uuid4()}"
        existing = self._events.get(event_id)
        if existing is None:
            event = EventRecord(
                event_id=event_id,
                source_system=request.source_system,
                source_agent_id=request.source_agent_id,
                source_role=request.source_role,
                event_type=request.event_type,
                severity=request.severity,
                message=request.message,
                metadata=dict(request.metadata),
            )
            self._events[event.event_id] = event
            return event
        existing.source_system = request.source_system
        existing.source_agent_id = request.source_agent_id
        existing.source_role = request.source_role
        existing.event_type = request.event_type
        existing.severity = request.severity
        existing.message = request.message
        existing.metadata = dict(request.metadata)
        existing.touch()
        return existing

    def list_events(self) -> List[EventRecord]:
        return [self._events[event_id] for event_id in sorted(self._events)]

    def get_event(self, event_id: str) -> EventRecord:
        event = self._events.get(event_id)
        if event is None:
            raise KeyError(event_id)
        return event
