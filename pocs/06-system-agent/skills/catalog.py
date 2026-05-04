from __future__ import annotations

from typing import Any


class SkillCatalog:
    def __init__(self, capabilities: dict[str, Any]) -> None:
        self.capabilities = capabilities

    def list_skills(self) -> list[str]:
        return list(self.capabilities.get("skills", []))

    def list_actions(self) -> list[str]:
        return list(self.capabilities.get("actions", []))

    def list_tracks(self) -> list[dict[str, Any]]:
        return list(self.capabilities.get("tracks", []))

    def list_constraints(self) -> list[str]:
        return list(self.capabilities.get("constraints", []))

