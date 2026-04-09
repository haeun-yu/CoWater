from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Header, HTTPException

from config import settings
from shared.auth_session import decode_session_token
from shared.command_auth import CommandActor, parse_command_actors, role_allows


@lru_cache(maxsize=1)
def _command_actor_map(raw: str) -> dict[str, CommandActor]:
    return parse_command_actors(raw)


def _resolve_actor(authorization: str | None) -> CommandActor:
    if not authorization:
        raise HTTPException(401, "Authorization header is required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Authorization must use Bearer token")

    actors = _command_actor_map(settings.command_tokens_json)
    actor = actors.get(token)
    if actor is not None:
        return actor

    return decode_session_token(
        token=token,
        secret=settings.auth_session_secret,
        issuer=settings.auth_session_issuer,
    )


def require_command_role(required_role: str) -> Callable[..., CommandActor]:
    def dependency(
        authorization: Annotated[str | None, Header()] = None,
    ) -> CommandActor:
        actor = _resolve_actor(authorization)
        if not role_allows(actor.role, required_role):
            raise HTTPException(403, f"'{required_role}' role is required")
        return actor

    return dependency
