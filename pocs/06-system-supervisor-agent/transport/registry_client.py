from __future__ import annotations

import json
import urllib.request
from typing import Any


def post_json(url: str, body: dict[str, Any], timeout: int = 5) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def put_json(url: str, body: dict[str, Any], timeout: int = 5) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


class RegistryClient:
    def __init__(self, config: dict[str, Any]) -> None:
        self.url = str(config.get("url") or "http://127.0.0.1:8003").rstrip("/")
        self.secret_key = str(config.get("secret_key") or "server-secret")
        self.required = bool(config.get("required", True))

    def register_device(self, name: str, tracks: list[dict[str, Any]], actions: list[str]) -> dict[str, Any]:
        return post_json(
            f"{self.url}/devices",
            {"secretKey": self.secret_key, "name": name, "tracks": tracks, "actions": {"custom": actions}},
        )

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

