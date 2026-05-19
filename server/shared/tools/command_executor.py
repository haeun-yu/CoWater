from __future__ import annotations

from agent.state import utc_now


class CommandExecutor:
    def __init__(self) -> None:
        self.history: list[dict] = []

    def execute(self, command: dict) -> dict:
        self.history.append({"at": utc_now(), "command": command})
        self.history = self.history[-20:]
        return {"delivered": True, "command": command, "at": utc_now()}

