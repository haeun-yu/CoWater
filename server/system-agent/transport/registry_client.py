from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def post_json(url: str, body: dict[str, Any], timeout: int = 5, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """POST JSON to server with error handling"""
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error posting to {url}: {e.code}")
        raise
    except urllib.error.URLError as e:
        logger.error(f"Network error posting to {url}: {e.reason}")
        raise
    except TimeoutError as e:
        logger.error(f"Timeout posting to {url}: {e}")
        raise


def put_json(url: str, body: dict[str, Any], timeout: int = 5, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """PUT JSON to server with error handling"""
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error putting to {url}: {e.code}")
        raise
    except urllib.error.URLError as e:
        logger.error(f"Network error putting to {url}: {e.reason}")
        raise
    except TimeoutError as e:
        logger.error(f"Timeout putting to {url}: {e}")
        raise


def get_json(url: str, timeout: int = 5) -> dict[str, Any]:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error getting {url}: {e.code}")
        raise
    except urllib.error.URLError as e:
        logger.error(f"Network error getting {url}: {e.reason}")
        raise
    except TimeoutError as e:
        logger.error(f"Timeout getting {url}: {e}")
        raise


class RegistryClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.url = str(config.get("url") or "http://127.0.0.1:8280").rstrip("/")
        self.secret_key = str(config.get("secret_key") or "server-secret")
        self.required = bool(config.get("required", True))

    def _internal_headers(self) -> dict[str, str]:
        return {"X-CoWater-Internal": "system-agent"}

    def register_device(
        self,
        name: str,
        tracks: list[dict[str, Any]],
        actions: list[str],
        *,
        device_type: str | None = None,
        layer: str | None = None,
        connectivity: str | None = None,
        location: dict[str, float] | None = None,
        requires_parent: bool = False,
        parent_id: int | None = None,
    ) -> dict[str, Any]:
        body = {
            "secretKey": self.secret_key,
            "name": name,
            "tracks": tracks,
            "actions": {"custom": actions},
        }
        if device_type is not None:
            body["device_type"] = device_type
        if layer is not None:
            body["layer"] = layer
        if connectivity is not None:
            body["connectivity"] = connectivity
        if location is not None:
            body["location"] = location
        if requires_parent:
            body["requires_parent"] = requires_parent
        return post_json(f"{self.url}/devices", body)

    def upsert_agent(
        self,
        registry_id: int,
        *,
        endpoint: str,
        command_endpoint: str,
        role: str,
        llm_enabled: bool,
        skills: list[str],
        actions: list[str],
        last_seen_at: str | None,
    ) -> dict[str, Any]:
        return put_json(
            f"{self.url}/devices/{registry_id}/agent",
            {
                "secretKey": self.secret_key,
                "endpoint": endpoint,
                "commandEndpoint": command_endpoint,
                "role": role,
                "llm_enabled": llm_enabled,
                "skills": skills,
                "available_actions": actions,
                "connected": True,
                "last_seen_at": last_seen_at,
            },
        )

    def get_assignment(self, registry_id: int) -> dict[str, Any]:
        return get_json(f"{self.url}/devices/{registry_id}/assignment")

    def get_device(self, registry_id: int) -> dict[str, Any]:
        return get_json(f"{self.url}/devices/{registry_id}")

    def list_devices(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/devices")

    def ingest_event(self, event: dict[str, Any]) -> dict[str, Any]:
        return post_json(f"{self.url}/events/ingest", event)

    def list_events(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/events")

    def get_event(self, event_id: str) -> dict[str, Any]:
        return get_json(f"{self.url}/events/{event_id}")

    def ingest_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
        return post_json(f"{self.url}/alerts/ingest", alert)

    def list_alerts(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/alerts")

    def get_alert(self, alert_id: str) -> dict[str, Any]:
        return get_json(f"{self.url}/alerts/{alert_id}")

    def acknowledge_alert(self, alert_id: str, approved: bool = True, notes: str | None = None) -> dict[str, Any]:
        body = {"approved": approved}
        if notes is not None:
            body["notes"] = notes
        return post_json(f"{self.url}/alerts/{alert_id}/ack", body)

    def list_device_roles(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/device-roles")

    def get_device_role(self, device_id: str | int) -> dict[str, Any]:
        return get_json(f"{self.url}/device-roles/{device_id}")

    def upsert_device_role(self, device_id: str | int, payload: dict[str, Any]) -> dict[str, Any]:
        return put_json(
            f"{self.url}/devices/{device_id}/role",
            payload,
            headers=self._internal_headers(),
        )

    def get_overview(self) -> dict[str, Any]:
        return {
            "devices": self.list_devices(),
            "device_roles": self.list_device_roles(),
            "operation_plans": self.list_operation_plans(),
            "insights": self.list_insights(),
            "approvals": self.list_approvals(),
            "mission_proposals": self.list_mission_proposals(),
            "missions": self.list_missions(),
        }

    def create_operation_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        return post_json(f"{self.url}/operation-plans", payload)

    def list_operation_plans(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/operation-plans")

    def get_operation_plan(self, operation_plan_id: str) -> dict[str, Any]:
        return get_json(f"{self.url}/operation-plans/{operation_plan_id}")

    def activate_operation_plan(self, operation_plan_id: str) -> dict[str, Any]:
        return post_json(
            f"{self.url}/operation-plans/{operation_plan_id}/activate",
            {},
            headers=self._internal_headers(),
        )

    def create_insight(self, payload: dict[str, Any]) -> dict[str, Any]:
        return post_json(f"{self.url}/insights", payload)

    def list_insights(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/insights")

    def create_approval(self, payload: dict[str, Any]) -> dict[str, Any]:
        return post_json(f"{self.url}/approvals", payload)

    def list_approvals(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/approvals")

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        return get_json(f"{self.url}/approvals/{approval_id}")

    def decide_approval(self, approval_id: str, *, approved: bool, decided_by: str = "user", notes: str | None = None) -> dict[str, Any]:
        body = {"approved": approved, "decided_by": decided_by}
        if notes is not None:
            body["notes"] = notes
        return post_json(f"{self.url}/approvals/{approval_id}/decision", body)

    def create_mission_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        return post_json(f"{self.url}/mission-proposals", payload)

    def list_mission_proposals(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/mission-proposals")

    def get_mission_proposal(self, proposal_id: str) -> dict[str, Any]:
        return get_json(f"{self.url}/mission-proposals/{proposal_id}")

    def create_mission(self, payload: dict[str, Any]) -> dict[str, Any]:
        return post_json(f"{self.url}/missions", payload)

    def list_missions(self) -> list[dict[str, Any]]:
        return get_json(f"{self.url}/missions")

    def get_mission(self, mission_id: str) -> dict[str, Any]:
        return get_json(f"{self.url}/missions/{mission_id}")

    def replace_mission(self, mission_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return put_json(f"{self.url}/missions/{mission_id}", payload)
