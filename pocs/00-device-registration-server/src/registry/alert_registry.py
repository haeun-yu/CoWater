from __future__ import annotations

from typing import Dict, List, Optional
from uuid import uuid4

from src.core.models import (
    AlertIngestRequest,
    AlertRecord,
    ResponseIngestRequest,
    ResponseRecord,
)


class AlertRegistry:
    def __init__(self) -> None:
        self._alerts: Dict[str, AlertRecord] = {}
        self._responses: Dict[str, ResponseRecord] = {}

    def ingest_alert(self, request: AlertIngestRequest) -> AlertRecord:
        alert_id = request.alert_id or f"alert-{uuid4()}"
        existing = self._alerts.get(alert_id)
        if existing is None:
            alert = AlertRecord(
                alert_id=alert_id,
                source_system=request.source_system,
                event_id=request.event_id,
                source_agent_id=request.source_agent_id,
                source_role=request.source_role,
                alert_type=request.alert_type,
                severity=request.severity,
                message=request.message,
                status=request.status,
                recommended_action=request.recommended_action,
                target_agent_id=request.target_agent_id,
                requires_user_approval=request.requires_user_approval,
                auto_remediated=request.auto_remediated,
                route_mode=request.route_mode,
                metadata=dict(request.metadata),
            )
            self._alerts[alert.alert_id] = alert
            return alert
        existing.source_system = request.source_system
        existing.event_id = request.event_id
        existing.source_agent_id = request.source_agent_id
        existing.source_role = request.source_role
        existing.alert_type = request.alert_type
        existing.severity = request.severity
        existing.message = request.message
        existing.status = request.status
        existing.recommended_action = request.recommended_action
        existing.target_agent_id = request.target_agent_id
        existing.requires_user_approval = request.requires_user_approval
        existing.auto_remediated = request.auto_remediated
        existing.route_mode = request.route_mode
        existing.metadata = dict(request.metadata)
        existing.touch()
        return existing

    def list_alerts(self) -> List[AlertRecord]:
        return [self._alerts[alert_id] for alert_id in sorted(self._alerts)]

    def get_alert(self, alert_id: str) -> AlertRecord:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise KeyError(alert_id)
        return alert

    def acknowledge_alert(self, alert_id: str, approved: bool = True, notes: Optional[str] = None) -> AlertRecord:
        alert = self.get_alert(alert_id)
        alert.touch("approved" if approved else "rejected")
        if notes:
            alert.metadata["notes"] = notes
        return alert

    def ingest_response(self, request: ResponseIngestRequest) -> ResponseRecord:
        response_id = request.response_id or f"response-{uuid4()}"
        response = ResponseRecord(
            response_id=response_id,
            alert_id=request.alert_id,
            action=request.action,
            target_agent_id=request.target_agent_id,
            target_endpoint=request.target_endpoint,
            route_mode=request.route_mode,
            status=request.status,
            reason=request.reason,
            task_id=request.task_id,
            dispatch_result=dict(request.dispatch_result),
            notes=request.notes,
        )
        self._responses[response.response_id] = response
        return response

    def list_responses(self) -> List[ResponseRecord]:
        return [self._responses[response_id] for response_id in sorted(self._responses)]

    def get_response(self, response_id: str) -> ResponseRecord:
        response = self._responses.get(response_id)
        if response is None:
            raise KeyError(response_id)
        return response
