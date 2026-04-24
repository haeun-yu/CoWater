from __future__ import annotations

"""A2A/HTTP 전송 헬퍼."""

from typing import Any

import httpx


async def post_json(url: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            if not resp.content:
                return {}
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:
            pass
        raise RuntimeError(detail or f"HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(str(exc)) from exc


async def send_a2a_message(url: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    body = {
        "message": {
            "role": "agent",
            "parts": [{"type": "data", "data": payload}],
        }
    }
    return await post_json(f"{url.rstrip('/')}/message:send", body, timeout=timeout)
