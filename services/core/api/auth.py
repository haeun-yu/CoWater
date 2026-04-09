from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import require_command_role
from config import settings
from shared.auth_session import issue_session_token
from shared.command_auth import CommandActor

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    token: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    actor: str
    role: str


class MeResponse(BaseModel):
    authenticated: bool
    actor: str
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    actor: Annotated[CommandActor, Depends(require_command_role("viewer"))],
):
    session_token = issue_session_token(
        actor=actor,
        secret=settings.auth_session_secret,
        issuer=settings.auth_session_issuer,
        expires_in_sec=settings.auth_session_expire_sec,
    )
    return LoginResponse(
        access_token=session_token,
        actor=actor.actor,
        role=actor.role,
    )


@router.get("/me", response_model=MeResponse)
async def me(
    actor: Annotated[CommandActor, Depends(require_command_role("viewer"))],
):
    return MeResponse(authenticated=True, actor=actor.actor, role=actor.role)


@router.post("/logout")
async def logout():
    return {"ok": True}
