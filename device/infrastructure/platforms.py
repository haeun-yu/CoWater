from __future__ import annotations

from dataclasses import dataclass
import importlib
import inspect
from pathlib import Path
from typing import Any


_DEVICE_TYPE_MAP = {
    "USV": "usv",
    "AUV": "auv",
    "ROV": "rov",
    "CONTROL_SHIP": "ship",
}

_TOOL_ALIASES = {
    "ship": {
        "camera_controller": "video_processor",
        "high_def_camera": "video_processor",
    }
}


def resolve_device_dir(device_type: str | None) -> str:
    raw_device_type = str(device_type or "").strip().upper()
    return _DEVICE_TYPE_MAP.get(raw_device_type, raw_device_type.lower() or "usv")


def _load_class(module_path: str, class_name: str) -> Any:
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _discover_tool_class(module: Any, preferred_name: str) -> Any | None:
    cls = getattr(module, preferred_name, None)
    if cls is not None:
        return cls
    candidates = [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if getattr(obj, "__module__", None) == module.__name__ and not obj.__name__.startswith("_")
    ]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        for candidate in candidates:
            if candidate.__name__.lower().endswith(preferred_name.lower()):
                return candidate
        return candidates[0]
    return None


@dataclass(frozen=True)
class DevicePlatform:
    device_type: str | None
    device_dir: str

    def build_telemetry_reader(self) -> Any:
        TelemetryReader = _load_class("tools.common.telemetry_reader", "TelemetryReader")
        return TelemetryReader()

    def build_simulator(self, simulation_config: dict[str, Any], tracks: list[dict[str, Any]]) -> Any:
        DeviceSimulator = _load_class(f"simulator.{self.device_dir}", "DeviceSimulator")
        return DeviceSimulator(simulation_config, tracks)

    def build_command_executor(self) -> Any:
        CommandExecutor = _load_class(f"tools.{self.device_dir}.command_executor", "CommandExecutor")
        return CommandExecutor()

    def load_tools(self, device_root: Path) -> dict[str, Any]:
        tools: dict[str, Any] = {}
        scan_targets = [
            (f"tools.{self.device_dir}", f"tools/{self.device_dir}"),
            ("tools.common", "tools/common"),
        ]

        for module_prefix, rel_dir in scan_targets:
            tools_dir = device_root / rel_dir
            if not tools_dir.exists():
                continue
            for py_file in tools_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                module_name = py_file.stem
                class_name = "".join(word.capitalize() for word in module_name.split("_"))
                try:
                    module = importlib.import_module(f"{module_prefix}.{module_name}")
                    cls = _discover_tool_class(module, class_name)
                    if cls:
                        tools[module_name] = cls()
                except Exception:
                    continue
        for source_name, alias_name in _TOOL_ALIASES.get(self.device_dir, {}).items():
            if source_name in tools and alias_name not in tools:
                tools[alias_name] = tools[source_name]
        return tools


def resolve_device_platform(device_type: str | None) -> DevicePlatform:
    return DevicePlatform(device_type=device_type, device_dir=resolve_device_dir(device_type))
