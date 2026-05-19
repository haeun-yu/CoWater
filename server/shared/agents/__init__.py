from __future__ import annotations

import os

from .registry import load_agents_recursively, registry, register_agent, register_plugin_agent, resolve_agent_profile


def _autoload() -> None:
    current_dir = os.path.dirname(__file__)
    load_agents_recursively(current_dir, "agents")


_autoload()

globals().update(registry.agents)
globals().update(registry.plugin_agents)

__all__ = sorted(set(list(registry.agents.keys()) + list(registry.plugin_agents.keys()) + ["resolve_agent_profile"]))
