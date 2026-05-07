from __future__ import annotations

from typing import Dict, List, Optional

from src.core.models import (
    AlertIngestRequest,
    AlertRecord,
)


class AlertRegistry:
    def __init__(self) -> None:
        self._alerts: Dict[str, AlertRecord] = {}

    def ingest_alert(self, request: AlertIngestRequest) -> AlertRecord:
        metadata = dict(request.metadata)
        fingerprint = str(
            metadata.get("fingerprint")
            or f"{request.event_id}:{request.alert_type}:{metadata.get('cause') or metadata.get('location') or request.message}"
        )
        for existing_alert in self._alerts.values():
            if str((existing_alert.metadata or {}).get("fingerprint") or "") == fingerprint:
                existing_alert.source_system = request.source_system
                existing_alert.event_id = request.event_id
                existing_alert.source_agent_id = request.source_agent_id
                existing_alert.source_role = request.source_role
                existing_alert.alert_type = request.alert_type
                existing_alert.severity = request.severity
                existing_alert.message = request.message
                existing_alert.recommended_action = request.recommended_action
                existing_alert.target_agent_id = request.target_agent_id
                existing_alert.requires_user_approval = request.requires_user_approval
                existing_alert.auto_remediated = request.auto_remediated
                existing_alert.route_mode = request.route_mode
                existing_alert.metadata = {**metadata, "fingerprint": fingerprint}
                existing_alert.touch()
                return existing_alert
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
                metadata={**metadata, "fingerprint": fingerprint},
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
        existing.metadata = {**metadata, "fingerprint": fingerprint}
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
        alert.touch("processing" if approved else "failed")
        if notes:
            alert.metadata["notes"] = notes
        return alert

    def reset(self) -> None:
        """모든 alert 초기화"""
        self._alerts.clear()
