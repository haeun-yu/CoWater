from __future__ import annotations

import asyncio

import httpx
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.alerts import AlertResponse, execute_alert_action
from config import settings
from shared.command_auth import CommandActor

from .command_parser import ParsedCommand


async def execute_command(
    *,
    db: AsyncSession,
    actor: CommandActor,
    parsed: ParsedCommand,
    source: str,
    context: dict,
) -> dict:
    if parsed.target_type == "alert":
        row = await execute_alert_action(
            db,
            parsed.target_id,
            parsed.arguments["action"],
            executor=actor.actor,
            source=source,
        )
        return {
            "kind": "alert",
            "alert": AlertResponse.from_model(row).model_dump(mode="json"),
        }

    if parsed.target_type == "agent":
        return await _execute_agent_command(actor, parsed, context)

    raise HTTPException(400, f"Unsupported command target type: {parsed.target_type}")


async def _execute_agent_command(
    actor: CommandActor,
    parsed: ParsedCommand,
    context: dict,
) -> dict:
    headers = {
        "Authorization": f"Bearer {actor.token}",
        "Content-Type": "application/json",
    }
    base_url = settings.agents_api_url.rstrip("/")
    timeout = settings.command_request_timeout_sec
    max_attempts = settings.command_request_max_attempts
    base_delay = settings.command_request_base_delay_sec

    async def _send_request(client: httpx.AsyncClient) -> httpx.Response:
        if parsed.intent == "agent.enable":
            return await client.patch(
                f"{base_url}/agents/{parsed.target_id}/enable",
                headers=headers,
            )
        if parsed.intent == "agent.disable":
            return await client.patch(
                f"{base_url}/agents/{parsed.target_id}/disable",
                headers=headers,
            )
        if parsed.intent == "agent.set_level":
            return await client.patch(
                f"{base_url}/agents/{parsed.target_id}/level",
                headers=headers,
                json={"level": parsed.arguments["level"]},
            )
        if parsed.intent == "agent.run":
            platform_id = parsed.arguments.get("platform_id") or context.get(
                "selected_platform_id"
            )
            if not platform_id:
                raise HTTPException(
                    400,
                    "Agent run commands require 'platform <platform_id>' or a selected platform context.",
                )
            return await client.post(
                f"{base_url}/agents/{parsed.target_id}/run",
                headers=headers,
                json={"platform_id": platform_id},
            )
        raise HTTPException(400, f"Unsupported agent intent: {parsed.intent}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = await _send_request(client)
                if response.status_code not in {502, 503, 504}:
                    break
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_error = exc

            if attempt == max_attempts:
                if last_error is not None:
                    raise HTTPException(
                        503,
                        f"Agent runtime unavailable at {base_url}. Please retry shortly.",
                    ) from last_error
                break

            await asyncio.sleep(base_delay * attempt)

        if response is None:
            raise HTTPException(
                503, "Agent runtime request failed before a response was received"
            )

    if response.is_success:
        return {
            "kind": "agent",
            "agent_id": parsed.target_id,
            "response": response.json(),
        }

    detail = None
    try:
        payload = response.json()
        detail = payload.get("detail") if isinstance(payload, dict) else payload
    except Exception:
        detail = response.text
    raise HTTPException(response.status_code, detail or "Agent runtime request failed")
