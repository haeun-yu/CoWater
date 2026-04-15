from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_command_role
from db import get_db
from services.audit_log import append_audit_log
from services.command_executor import execute_command
from services.command_parser import ParsedCommand, parse_command
from shared.command_auth import CommandActor, role_allows

router = APIRouter(prefix="/commands", tags=["commands"])


class CommandRequest(BaseModel):
    text: str
    source: Literal["text", "voice"] = "text"
    dry_run: bool = False
    context: dict | None = None


class ParsedCommandResponse(BaseModel):
    intent: str
    summary: str
    required_role: str
    target_type: str
    target_id: str
    arguments: dict

    @classmethod
    def from_parsed(cls, parsed: ParsedCommand) -> "ParsedCommandResponse":
        return cls(
            intent=parsed.intent,
            summary=parsed.summary,
            required_role=parsed.required_role,
            target_type=parsed.target_type,
            target_id=parsed.target_id,
            arguments=parsed.arguments,
        )


class CommandResponse(BaseModel):
    status: Literal["dry_run", "executed"]
    source: Literal["text", "voice"]
    actor: str
    allowed: bool
    parsed: ParsedCommandResponse
    result: dict | None = None


class CommandAuthStatusResponse(BaseModel):
    authenticated: bool
    actor: str | None = None
    role: Literal["viewer", "operator", "admin"] | None = None


def _request_meta(request: Request) -> dict:
    client = request.client.host if request.client else None
    return {
        "remote_ip": client,
        "user_agent": request.headers.get("user-agent"),
    }


@router.post("/preview", response_model=ParsedCommandResponse)
async def preview_command(body: CommandRequest):
    """인증 없이 명령어를 파싱하여 미리보기를 반환한다. 실행하지 않음.

    - 200: 유효한 명령어 → 파싱 결과 반환
    - 400: 명령어로 인식되지 않음 (일반 텍스트/대화)
    """
    parsed = parse_command(body.text)
    return ParsedCommandResponse.from_parsed(parsed)


@router.post("", response_model=CommandResponse)
async def run_command(
    body: CommandRequest,
    request: Request,
    actor: Annotated[CommandActor, Depends(require_command_role("viewer"))],
    db: AsyncSession = Depends(get_db),
):
    context = body.context or {}
    parsed = parse_command(body.text)

    audit_payload = {
        "text": body.text,
        "source": body.source,
        "context": context,
        "parsed": ParsedCommandResponse.from_parsed(parsed).model_dump(mode="json"),
        **_request_meta(request),
    }
    await append_audit_log(
        event_type="command.received",
        actor=actor.actor,
        entity_type=parsed.target_type,
        entity_id=parsed.target_id,
        payload=audit_payload,
    )

    allowed = role_allows(actor.role, parsed.required_role)
    if body.dry_run:
        return CommandResponse(
            status="dry_run",
            source=body.source,
            actor=actor.actor,
            allowed=allowed,
            parsed=ParsedCommandResponse.from_parsed(parsed),
            result=None,
        )

    if not allowed:
        await append_audit_log(
            event_type="command.denied",
            actor=actor.actor,
            entity_type=parsed.target_type,
            entity_id=parsed.target_id,
            payload={
                **audit_payload,
                "actor_role": actor.role,
                "required_role": parsed.required_role,
                "reason": "insufficient_role",
            },
        )
        raise HTTPException(403, f"'{parsed.required_role}' role is required")

    try:
        result = await execute_command(
            db=db,
            actor=actor,
            parsed=parsed,
            source=body.source,
            context=context,
        )
        await db.commit()
    except HTTPException as exc:
        await db.rollback()
        await append_audit_log(
            event_type="command.failed",
            actor=actor.actor,
            entity_type=parsed.target_type,
            entity_id=parsed.target_id,
            payload={
                **audit_payload,
                "actor_role": actor.role,
                "detail": exc.detail,
                "status_code": exc.status_code,
            },
        )
        raise
    except Exception as exc:
        await db.rollback()
        await append_audit_log(
            event_type="command.failed",
            actor=actor.actor,
            entity_type=parsed.target_type,
            entity_id=parsed.target_id,
            payload={
                **audit_payload,
                "actor_role": actor.role,
                "detail": str(exc),
                "status_code": 500,
            },
        )
        raise

    await append_audit_log(
        event_type="command.executed",
        actor=actor.actor,
        entity_type=parsed.target_type,
        entity_id=parsed.target_id,
        payload={
            **audit_payload,
            "actor_role": actor.role,
            "result": result,
        },
    )
    return CommandResponse(
        status="executed",
        source=body.source,
        actor=actor.actor,
        allowed=True,
        parsed=ParsedCommandResponse.from_parsed(parsed),
        result=result,
    )


@router.get("/auth-status", response_model=CommandAuthStatusResponse)
async def command_auth_status(
    actor: Annotated[CommandActor, Depends(require_command_role("viewer"))],
):
    return CommandAuthStatusResponse(
        authenticated=True,
        actor=actor.actor,
        role=actor.role,
    )
