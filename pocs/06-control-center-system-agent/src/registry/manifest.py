from __future__ import annotations

"""Agent manifest / card 빌더."""

from typing import Any

from ..core.config import DEFAULT_A2A_BINDING, utc_now_iso


def build_agent_manifest(hub: Any) -> dict[str, Any]:
    base_url = f"http://{hub.settings['server']['host']}:{hub.settings['server']['port']}"
    llm_cfg = hub.analysis_settings.get("llm") or {}
    llm_enabled = bool(str(llm_cfg.get("provider") or "").strip() and str(llm_cfg.get("model") or "").strip())
    return {
        "agent_id": hub.state.agent_id,
        "role": hub.state.role,
        "mode": "dynamic",
        "endpoint": base_url,
        "command_endpoint": f"{base_url}/message:send",
        "analysis": {
            "strategy": "hybrid" if llm_enabled else "rule",
            "llm_enabled": llm_enabled,
            "llm": llm_cfg if llm_enabled else {},
        },
        "registry": hub.state.registry_snapshot,
        "skills": [
            "ingest_system_event",
            "analyze_system_signal",
            "route_remediation",
            "track_response",
            "sync_child_registry",
            "plan_mission",
            "assign_regional_orchestrator",
            "direct_route_override",
        ],
        "tools": [
            "event_store",
            "alert_store",
            "response_store",
            "mission_store",
            "child_registry",
            "route_planner",
            "registry_sync",
        ],
        "constraints": [
            "always_generate_alerts",
            "respect_user_approval_boundary",
            "prefer_mid_tier_routing",
            "direct_route_requires_authority",
        ],
        "available_actions": [
            "event.report",
            "system.event",
            "system.alert",
            "response.plan",
            "response.dispatch",
            "task.assign",
            "task.accept",
            "task.complete",
            "task.fail",
            "status.report",
            "task.escalate",
        ],
        "supported_inputs": ["application/json", "text/plain"],
        "supported_outputs": ["application/json", "text/plain"],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "direct_route_allowed": hub.state.direct_route_allowed,
            "llm_enabled": llm_enabled,
        },
        "parent_id": hub.state.parent_id,
        "parent_endpoint": hub.state.parent_endpoint,
        "children": {},
        "analysis_settings": hub.analysis_settings,
        "updated_at": utc_now_iso(),
    }


def build_agent_card(hub: Any) -> dict[str, Any]:
    base_url = f"http://{hub.settings['server']['host']}:{hub.settings['server']['port']}"
    return {
        "name": hub.state.agent_id,
        "displayName": "CoWater System Center Agent",
        "description": "Top-tier system control agent for ingesting system events, analyzing incidents, and routing remediation through the regional orchestrator or device agents.",
        "url": base_url,
        "version": "1.0.0",
        "protocolVersion": "1.0.0",
        "supportedInterfaces": [
            {
                "url": base_url,
                "protocolBinding": DEFAULT_A2A_BINDING,
                "protocolVersion": "1.0.0",
            }
        ],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "skills": [
            {
                "id": "plan_mission",
                "name": "Plan Mission",
                "description": "Create and manage mission records for downstream agents.",
            },
            {
                "id": "ingest_system_event",
                "name": "Ingest System Event",
                "description": "Accept events from the system layer, dashboard, or upstream agents.",
            },
            {
                "id": "analyze_system_signal",
                "name": "Analyze System Signal",
                "description": "Classify incidents by rule or LLM before producing an alert.",
            },
            {
                "id": "route_remediation",
                "name": "Route Remediation",
                "description": "Delegate remediation to the regional orchestrator or directly to a device agent when allowed.",
            },
            {
                "id": "track_response",
                "name": "Track Response",
                "description": "Persist alert and response lifecycle updates for operational visibility.",
            },
            {
                "id": "direct_route_override",
                "name": "Direct Route Override",
                "description": "Bypass the mid-tier when scope and authority allow direct control.",
            },
        ],
    }
