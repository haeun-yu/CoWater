from __future__ import annotations

from typing import Any

import httpx


async def post_json(url: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    """주어진 URL로 JSON POST 요청을 비동기로 발송한다."""
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
    """A2A 표준 메시지 형식으로 래핑하여 POST /message:send 로 발송한다."""
    body = {
        "message": {
            "role": "agent",
            "parts": [{"type": "data", "data": payload}],
        }
    }
    return await post_json(f"{url.rstrip('/')}/message:send", body, timeout=timeout)


async def publish_alert(url: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    """알림 원장(03)으로 alert를 등록한다."""
    return await post_json(f"{url.rstrip('/')}/alerts/ingest", payload, timeout=timeout)


async def publish_response(url: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    """알림 원장(03)으로 response를 등록한다."""
    return await post_json(f"{url.rstrip('/')}/responses/ingest", payload, timeout=timeout)


async def acknowledge_alert(url: str, alert_id: str, payload: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    """알림 원장(03)에서 alert 승인/반려를 기록한다."""
    return await post_json(f"{url.rstrip('/')}/alerts/{alert_id}/ack", payload, timeout=timeout)
