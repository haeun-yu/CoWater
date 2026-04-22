from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from uuid import uuid4


ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


@dataclass
class CommandResult:
    command_id: str
    role: str
    command: str
    allowed: bool
    required_role: str
    event_type: str
    payload: dict


def parse_command(command: str) -> tuple[str, str, dict]:
    lowered = command.lower().strip()
    if "approve" in lowered and "rov" in lowered:
        return "operator", "respond.command.approve_rov_deploy", {"action": "approve_rov_deploy"}
    if lowered.startswith("agent ") and "disable" in lowered:
        return "admin", "respond.command.agent_config", {"action": "disable_agent"}
    if lowered.startswith("status"):
        return "viewer", "command.query.status", {"action": "query_status"}
    return "operator", "respond.command.generic", {"action": "generic_command"}


def execute(role: str, command: str) -> CommandResult:
    required_role, event_type, payload = parse_command(command)
    allowed = ROLE_RANK[role] >= ROLE_RANK[required_role]
    return CommandResult(
        command_id=str(uuid4()),
        role=role,
        command=command,
        allowed=allowed,
        required_role=required_role,
        event_type=event_type if allowed else "command.denied",
        payload=payload if allowed else {"reason": f"requires {required_role}"},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=sorted(ROLE_RANK), default="viewer")
    parser.add_argument("command", nargs="+")
    args = parser.parse_args()
    result = execute(args.role, " ".join(args.command))
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
