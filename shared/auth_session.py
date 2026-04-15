from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException

from .command_auth import CommandActor


def issue_session_token(
    *,
    actor: CommandActor,
    secret: str,
    issuer: str,
    expires_in_sec: int,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": actor.actor,
        "role": actor.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in_sec)).timestamp()),
        "iss": issuer,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_session_token(*, token: str, secret: str, issuer: str) -> CommandActor:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], issuer=issuer)
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired session token") from exc

    actor = payload.get("sub")
    role = payload.get("role")
    if not isinstance(actor, str) or not actor.strip():
        raise HTTPException(401, "Invalid session subject")
    if role not in {"viewer", "operator", "admin"}:
        raise HTTPException(401, "Invalid session role")

    return CommandActor(token=token, actor=actor, role=role)
