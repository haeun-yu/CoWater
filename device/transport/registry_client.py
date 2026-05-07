from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from urllib.parse import urlencode
from typing import Any

logger = logging.getLogger(__name__)


def post_json(url: str, body: dict[str, Any], timeout: int = 5) -> dict[str, Any]:
    """POST JSON to server with error handling"""
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
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


def put_json(url: str, body: dict[str, Any], timeout: int = 5) -> dict[str, Any]:
    """PUT JSON to server with error handling"""
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
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


def patch_json(url: str, body: dict[str, Any], timeout: int = 5) -> dict[str, Any]:
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PATCH")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
            return json.loads(payload or b"{}")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error patching {url}: {e.code}")
        raise
    except urllib.error.URLError as e:
        logger.error(f"Network error patching {url}: {e.reason}")
        raise
    except TimeoutError as e:
        logger.error(f"Timeout patching to {url}: {e}")
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

    def rename_device(self, registry_id: int, name: str) -> dict[str, Any]:
        return patch_json(f"{self.url}/devices/{registry_id}", {"name": name})

    def ingest_alert(self, alert: dict[str, Any]) -> None:
        """Critical rule 발동 시 서버 alert registry에 등록"""
        try:
            post_json(f"{self.url}/alerts/ingest", alert, timeout=3)
        except Exception as e:
            logger.debug(f"Alert 전송 실패 (non-critical): {e}")

    def log_a2a_message(
        self,
        direction: str,
        from_agent_id: str,
        to_agent_id: str,
        message_type: str,
        task_id: str | None,
        mission_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        """A2A 메시지 로깅 (Registry Server에 전송)"""
        try:
            params = {
                "direction": direction,
                "from_agent_id": from_agent_id,
                "to_agent_id": to_agent_id,
                "message_type": message_type,
            }
            if task_id:
                params["task_id"] = task_id
            if mission_id:
                params["mission_id"] = mission_id

            query = urlencode(params)
            url = f"{self.url}/a2a-logs/ingest"
            if query:
                url = f"{url}?{query}"
            post_json(url, payload, timeout=3)
        except Exception as e:
            logger.debug(f"A2A 로깅 전송 실패 (non-critical): {e}")

    def ingest_event(self, event: dict[str, Any]) -> None:
        """Event 저장 (Registry Server) - Ch.15, 16"""
        try:
            post_json(f"{self.url}/events/ingest", event, timeout=3)
        except Exception as e:
            logger.debug(f"Event ingestion failed (non-critical): {e}")
