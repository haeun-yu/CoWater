from __future__ import annotations

"""시스템 알림 기록과 승인 처리."""

from typing import Any, Optional

from ..core.config import utc_now_iso


def record_event(hub: Any, event: Any) -> Any:
    hub.state.events.append(event)
    hub.state.events = hub.state.events[-hub.notification_settings.get("retain", 100):]
    hub.state.last_seen_at = utc_now_iso()
    hub.state.remember({"kind": "system.event", "at": utc_now_iso(), "event": event.to_dict()})
    return event


def record_alert(hub: Any, alert: Any) -> Any:
    hub.state.alerts.append(alert)
    hub.state.alerts = hub.state.alerts[-hub.notification_settings.get("retain", 100):]
    hub.state.remember({"kind": "system.alert", "at": utc_now_iso(), "alert": alert.to_dict()})
    return alert


def get_alert(hub: Any, alert_id: str) -> Any:
    for alert in hub.state.alerts:
        if alert.alert_id == alert_id:
            return alert
    raise KeyError(alert_id)


def acknowledge_alert(hub: Any, alert_id: str, approved: bool = True, notes: Optional[str] = None) -> Any:
    alert = get_alert(hub, alert_id)
    alert.touch("approved" if approved else "rejected")
    if notes:
        alert.metadata["notes"] = notes
    hub.state.remember(
        {
            "kind": "system.alert.ack",
            "at": utc_now_iso(),
            "alert_id": alert_id,
            "approved": approved,
            "notes": notes,
        }
    )
    return alert
