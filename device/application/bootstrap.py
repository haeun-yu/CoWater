from __future__ import annotations

from pathlib import Path

from agent.runtime import AgentRuntime
from infrastructure.platforms import DevicePlatform, resolve_device_platform


def build_device_runtime(config_path: Path | str, *, platform: DevicePlatform | None = None) -> AgentRuntime:
    return AgentRuntime(Path(config_path), platform=platform)


def build_device_platform(device_type: str | None = None) -> DevicePlatform:
    return resolve_device_platform(device_type)
