from __future__ import annotations

from pathlib import Path

from agent.runtime import AgentRuntime


def build_agent_runtime(config_path: Path | str, overrides: dict | None = None) -> AgentRuntime:
    return AgentRuntime(Path(config_path), overrides=overrides)
