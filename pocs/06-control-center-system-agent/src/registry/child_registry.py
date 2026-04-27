from __future__ import annotations

"""하위 에이전트 레지스트리 관리."""

from typing import Any
from uuid import uuid4

from ..core.config import utc_now_iso


def child_manifest(hub: Any, payload: Any) -> dict[str, Any]:
    available_actions = list(payload.available_actions or payload.capabilities)
    skills = list(payload.skills or available_actions)
    return {
        "agent_id": payload.agent_id,
        "role": payload.role,
        "mode": payload.mode,
        "endpoint": payload.endpoint,
        "command_endpoint": payload.command_endpoint,
        "skills": skills,
        "tools": list(payload.tools),
        "constraints": list(payload.constraints),
        "available_actions": available_actions,
        "supported_inputs": list(payload.supported_inputs),
        "supported_outputs": list(payload.supported_outputs),
        "capabilities": list(payload.capabilities),
        "transport": "command" if payload.command_endpoint else "a2a",
        "parent_id": getattr(payload, "parent_id", None) or hub.state.agent_id,
        "parent_endpoint": getattr(payload, "parent_endpoint", None) or hub.state.parent_endpoint,
        "notes": payload.notes,
        "last_seen_at": utc_now_iso(),
    }


def register_child(hub: Any, payload: Any) -> Any:
    from ..core.models import ChildAgentRecord

    child = ChildAgentRecord(
        agent_id=payload.agent_id,
        role=payload.role,
        endpoint=payload.endpoint,
        command_endpoint=payload.command_endpoint,
        capabilities=list(payload.capabilities or payload.available_actions),
        transport="command" if payload.command_endpoint else "a2a",
        status="registered",
        last_seen_at=utc_now_iso(),
        notes=payload.notes,
    )
    hub._child_index[child.agent_id] = child
    hub._manual_child_ids.add(child.agent_id)
    hub.state.children = list(hub._child_index.values())
    hub.state.agent_manifest.setdefault("children", {})
    hub.state.agent_manifest["children"][child.agent_id] = child_manifest(hub, payload)
    hub.state.remember({"kind": "child.registered", "at": utc_now_iso(), "child": child.to_dict()})
    return child


def heartbeat_child(hub: Any, agent_id: str) -> Any:
    child = hub._child_index.get(agent_id)
    if child is None:
        raise KeyError(agent_id)
    child.status = "online"
    child.last_seen_at = utc_now_iso()
    hub.state.children = list(hub._child_index.values())
    if agent_id in hub.state.agent_manifest.get("children", {}):
        hub.state.agent_manifest["children"][agent_id]["status"] = "online"
        hub.state.agent_manifest["children"][agent_id]["last_seen_at"] = child.last_seen_at
    hub.state.remember({"kind": "child.heartbeat", "at": utc_now_iso(), "agent_id": agent_id})
    return child


async def sync_children_from_registry(hub: Any) -> dict[str, Any]:
    import httpx

    registry_url = str(hub.registry_settings.get("device_registry_url") or "").rstrip("/")
    if not registry_url:
        return {"synced": False, "reason": "device_registry_url not configured"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{registry_url}/devices")
            resp.raise_for_status()
            body = resp.json()
            devices = body if isinstance(body, list) else []
    except Exception as exc:
        hub.state.remember({"kind": "registry.sync_failed", "at": utc_now_iso(), "error": str(exc)})
        return {"synced": False, "error": str(exc)}

    synced_children: list[dict[str, Any]] = []
    for child_id in list(hub._registry_child_ids):
        hub._child_index.pop(child_id, None)
        if child_id in hub.state.agent_manifest.get("children", {}):
            hub.state.agent_manifest["children"].pop(child_id, None)
    hub._registry_child_ids = set()
    hub.state.agent_manifest.setdefault("children", {})
    for device in devices:
        if not isinstance(device, dict):
            continue
        agent = device.get("agent") if isinstance(device.get("agent"), dict) else {}
        agent_id = str(device.get("token") or device.get("name") or device.get("id") or "")
        role = str(agent.get("role") or "unknown")
        endpoint = agent.get("endpoint")
        command_endpoint = agent.get("command_endpoint")
        if not agent_id or not endpoint:
            continue
        child = ChildAgentRecord(
            agent_id=agent_id,
            role=role,
            endpoint=endpoint,
            command_endpoint=command_endpoint,
            capabilities=list(agent.get("available_actions") or device.get("actions", {}).get("core") or []),
            transport="command" if command_endpoint else "a2a",
            status="online" if agent.get("connected", False) else "registered",
            last_seen_at=agent.get("last_seen_at") or device.get("updated_at"),
            notes=device.get("name"),
        )
        hub._child_index[child.agent_id] = child
        hub._registry_child_ids.add(child.agent_id)
        synced_children.append(child.to_dict())
        hub.state.agent_manifest["children"][child.agent_id] = {
            "agent_id": child.agent_id,
            "role": child.role,
            "endpoint": child.endpoint,
            "command_endpoint": command_endpoint,
            "skills": list(agent.get("skills") or []),
            "tools": list(agent.get("tools") or []),
            "constraints": list(agent.get("constraints") or []),
            "available_actions": list(agent.get("available_actions") or []),
            "capabilities": list(agent.get("available_actions") or device.get("actions", {}).get("core") or []),
            "transport": child.transport,
            "connected": bool(agent.get("connected", False)),
            "connected_at": agent.get("connected_at"),
            "last_seen_at": child.last_seen_at,
            "notes": device.get("name"),
            "source_device_id": device.get("id"),
        }
    hub.state.children = list(hub._child_index.values())
    hub.state.registry_snapshot["last_sync_at"] = utc_now_iso()
    hub.state.registry_snapshot["synced_children"] = len(synced_children)
    hub.state.remember({"kind": "registry.synced", "at": utc_now_iso(), "children": synced_children})
    return {"synced": True, "children": synced_children, "count": len(synced_children)}
