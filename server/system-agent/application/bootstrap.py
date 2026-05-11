from __future__ import annotations

from pathlib import Path

from agent.runtime import AgentRuntime


def build_agent_runtime(config_path: Path | str) -> AgentRuntime:
    return AgentRuntime(Path(config_path))

