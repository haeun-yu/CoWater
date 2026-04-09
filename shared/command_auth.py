from __future__ import annotations

import json
from dataclasses import dataclass


ROLE_ORDER = {"viewer": 0, "operator": 1, "admin": 2}


@dataclass(frozen=True)
class CommandActor:
    token: str
    actor: str
    role: str


def parse_command_actors(raw: str) -> dict[str, CommandActor]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("COMMAND_TOKENS_JSON must be valid JSON") from exc

    if not isinstance(data, dict):
        raise ValueError("COMMAND_TOKENS_JSON must be a JSON object")

    actors: dict[str, CommandActor] = {}
    for token, info in data.items():
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Command token keys must be non-empty strings")
        if not isinstance(info, dict):
            raise ValueError("Each command token entry must be an object")

        actor = info.get("actor")
        role = info.get("role")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("Each command token entry requires a non-empty 'actor'")
        if role not in ROLE_ORDER:
            raise ValueError(
                "Each command token entry requires role viewer/operator/admin"
            )

        actors[token] = CommandActor(token=token, actor=actor, role=role)

    return actors


def role_allows(actual_role: str, required_role: str) -> bool:
    if actual_role not in ROLE_ORDER or required_role not in ROLE_ORDER:
        return False
    return ROLE_ORDER[actual_role] >= ROLE_ORDER[required_role]
