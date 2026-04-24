from __future__ import annotations

"""시스템 이벤트 ingest 및 대응 흐름."""

from typing import Any, Optional
from uuid import uuid4

from ..core.analysis import analyze_event
from ..core.alerts import record_alert, record_event
from ..core.config import utc_now_iso
from ..core.responses import record_response
from ..core.models import SystemAlertRecord, SystemEventRecord, SystemResponseRecord
from ..transport.a2a import publish_alert as publish_alert_to_store
from ..transport.a2a import publish_response as publish_response_to_store


async def ingest_system_event(hub: Any, payload: Any, routed_via: Optional[str] = None) -> dict[str, Any]:
    event = hub._build_event_record(payload)
    record_event(hub, event)
    analysis = await analyze_event(hub, event)
    event.decision_strategy = str(analysis.get("analysis_source") or event.decision_strategy)
    event.recommended_action = analysis.get("recommended_action")
    event.target_agent_id = analysis.get("target_agent_id") or event.target_agent_id
    event.route_mode = analysis.get("route_mode")
    event.user_approval_required = bool(analysis.get("requires_user_approval", event.user_approval_required))
    event.touch("analyzed")

    alert = SystemAlertRecord(
        alert_id=f"alert-{uuid4()}",
        event_id=event.event_id,
        alert_type=str(analysis.get("alert_type") or "system_event"),
        severity=str(analysis.get("severity") or event.severity),
        message=str(analysis.get("message") or event.summary),
        status="waiting" if event.user_approval_required else "planned",
        recommended_action=event.recommended_action,
        target_agent_id=event.target_agent_id,
        requires_user_approval=event.user_approval_required,
        auto_remediated=False,
        metadata={
            "flow_id": event.flow_id,
            "causation_id": event.causation_id,
            "source_role": event.source_role,
            "analysis_strategy": event.decision_strategy,
            "analysis": analysis,
            "routed_via": routed_via,
        },
    )
    record_alert(hub, alert)
    alert_store_url = str(hub.notification_settings.get("notification_store_url") or "").rstrip("/")
    if alert_store_url:
        try:
            await publish_alert_to_store(alert_store_url, alert.to_dict())
        except Exception as exc:
            hub.state.remember({"kind": "alert.store_failed", "at": utc_now_iso(), "error": str(exc), "alert_id": alert.alert_id})

    response: Optional[SystemResponseRecord] = None
    auto_response_allowed = bool(hub.analysis_settings.get("auto_response", True))
    if payload.auto_response is not None:
        auto_response_allowed = bool(payload.auto_response)
    if event.recommended_action and event.recommended_action != "alert_operator" and auto_response_allowed and not event.user_approval_required:
        target = hub._find_child_by_agent_id(event.target_agent_id or "") if event.target_agent_id else None
        if target is None and analysis.get("target_role"):
            target = hub._find_child_by_role(str(analysis.get("target_role")))
        if target is None:
            direct_roles = set(hub.registry_settings.get("direct_device_roles") or [])
            if event.source_role in direct_roles:
                target = hub._find_child_by_role(event.source_role)
            if target is None and analysis.get("target_role") in direct_roles:
                target = hub._find_child_by_role(str(analysis.get("target_role")))
        if target is None:
            regional_role = str(hub.registry_settings.get("control_ship_role") or "regional_orchestrator")
            target = hub._find_child_by_role(regional_role)

        if target is not None:
            route_mode = "via_regional_orchestrator" if target.role == str(hub.registry_settings.get("control_ship_role") or "regional_orchestrator") else "direct"
            response = SystemResponseRecord(
                response_id=f"response-{uuid4()}",
                alert_id=alert.alert_id,
                action=str(event.recommended_action),
                target_agent_id=target.agent_id,
                target_endpoint=target.endpoint,
                route_mode=route_mode,
                status="dispatching",
                reason=str(analysis.get("llm_reason") or event.summary or "rule-based remediation"),
                task_id=event.flow_id or event.event_id,
                dispatch_result={},
                notes="auto response" if auto_response_allowed else "manual response",
            )
            response = record_response(hub, response)
            if alert_store_url:
                try:
                    await publish_response_to_store(alert_store_url, response.to_dict())
                except Exception as exc:
                    hub.state.remember({"kind": "response.store_failed", "at": utc_now_iso(), "error": str(exc), "response_id": response.response_id})
            from ..core.routing import make_task_assign_message

            message = make_task_assign_message(hub, event, alert, response, target, analysis, route_mode)
            dispatch_result = await hub._dispatch_message(message, target_id=target.agent_id, target_endpoint=target.endpoint)
            response.dispatch_result = dispatch_result
            response.touch("dispatched" if dispatch_result.get("status") == "sent" else "queued")
            alert.auto_remediated = dispatch_result.get("status") == "sent"
            alert.touch("in_progress" if alert.auto_remediated else "queued")
            event.touch("responding")
        else:
            event.touch("waiting_user")
    else:
        event.touch("waiting_user" if event.user_approval_required else "analyzed")
        if event.recommended_action == "alert_operator" or hub.notification_settings.get("always_alert", True):
            alert.touch("waiting_user" if event.user_approval_required else "notified")

    hub.state.registry_snapshot["last_event_at"] = utc_now_iso()
    hub.state.context["last_event"] = event.to_dict()
    hub.state.context["last_alert"] = alert.to_dict()
    if response is not None:
        hub.state.context["last_response"] = response.to_dict()
    hub.state.remember(
        {
            "kind": "system.ingested",
            "at": utc_now_iso(),
            "event": event.to_dict(),
            "alert": alert.to_dict(),
            "response": response.to_dict() if response else None,
        }
    )
    return {
        "event": event.to_dict(),
        "alert": alert.to_dict(),
        "response": response.to_dict() if response else None,
        "analysis": analysis,
        "agent": hub.state.to_dict(),
    }
