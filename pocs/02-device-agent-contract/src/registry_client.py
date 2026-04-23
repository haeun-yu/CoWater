from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RegistryAgentRegistration:
    secret_key: str
    endpoint: str
    command_endpoint: str
    role: str
    mode: str
    skills: list[str]
    available_actions: list[str]
    connected: bool = True
    last_seen_at: Optional[str] = None
    device_name: Optional[str] = None
    device_type: Optional[str] = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "secretKey": self.secret_key,
            "endpoint": self.endpoint,
            "commandEndpoint": self.command_endpoint,
            "role": self.role,
            "mode": self.mode,
            "skills": list(self.skills),
            "available_actions": list(self.available_actions),
            "connected": self.connected,
            "last_seen_at": self.last_seen_at,
            "device_name": self.device_name,
            "device_type": self.device_type,
        }


class RegistryClient:
    def __init__(self, base_url: str, secret_key: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.secret_key = secret_key
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        body = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail", "")
            except Exception:
                pass
            raise RuntimeError(detail or f"HTTP {exc.code}") from exc

    async def fetch_device(self, device_id: int) -> dict[str, Any]:
        return await asyncio.to_thread(self._request, "GET", f"/devices/{device_id}")

    async def upsert_agent(self, device_id: int, registration: RegistryAgentRegistration) -> dict[str, Any]:
        payload = registration.to_payload()
        return await asyncio.to_thread(self._request, "PUT", f"/devices/{device_id}/agent", payload)

    async def detach_agent(self, device_id: int) -> dict[str, Any]:
        query = urllib.parse.urlencode({"secretKey": self.secret_key})
        return await asyncio.to_thread(self._request, "DELETE", f"/devices/{device_id}/agent?{query}")
