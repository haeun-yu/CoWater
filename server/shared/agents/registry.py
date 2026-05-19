from __future__ import annotations

import functools
import importlib
import inspect
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Literal, Optional


@dataclass
class FunctionInfo:
    name: str
    func_name: str
    func: Callable[..., Any]
    args: list[str]
    docstring: Optional[str]
    body: str
    return_type: Optional[str]
    file_path: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("func", None)
        return data


class Registry:
    _instance = None
    _registry: Dict[str, Dict[str, Callable[..., Any]]] = {
        "agents": {},
        "plugin_agents": {},
    }
    _registry_info: Dict[str, Dict[str, FunctionInfo]] = {
        "agents": {},
        "plugin_agents": {},
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(
        self,
        type: Literal["agent", "plugin_agent"],
        name: str | None = None,
        func_name: str | None = None,
    ):
        def decorator(func: Callable[..., Any]):
            nonlocal name
            if name is None:
                name = func.__name__
            registry_type = f"{type}s"
            key = func_name or func.__name__
            self._registry[registry_type][key] = func
            if name:
                self._registry[registry_type][name] = func

            try:
                file_path = os.path.abspath(inspect.getfile(func))
            except Exception:
                file_path = "Unknown"
            signature = inspect.signature(func)
            args = list(signature.parameters.keys())
            docstring = inspect.getdoc(func)
            try:
                source_lines = inspect.getsource(func).splitlines()
                body = "\n".join(source_lines[1:])
            except Exception:
                body = ""
            return_type = None
            if signature.return_annotation != inspect.Signature.empty:
                return_type = str(signature.return_annotation)
            self._registry_info[registry_type][name] = FunctionInfo(
                name=name,
                func_name=key,
                func=func,
                args=args,
                docstring=docstring,
                body=body,
                return_type=return_type,
                file_path=file_path,
            )
            return func

        return decorator

    @property
    def agents(self) -> Dict[str, Callable[..., Any]]:
        return self._registry["agents"]

    @property
    def plugin_agents(self) -> Dict[str, Callable[..., Any]]:
        return self._registry["plugin_agents"]

    @property
    def agents_info(self) -> Dict[str, FunctionInfo]:
        return self._registry_info["agents"]

    @property
    def plugin_agents_info(self) -> Dict[str, FunctionInfo]:
        return self._registry_info["plugin_agents"]

    def get_agent(self, name: str) -> Callable[..., Any] | None:
        return self._registry["agents"].get(name) or self._registry["plugin_agents"].get(name)


registry = Registry()


def register_agent(name: str | None = None, func_name: str | None = None):
    return registry.register(type="agent", name=name, func_name=func_name)


def register_plugin_agent(name: str | None = None, func_name: str | None = None):
    return registry.register(type="plugin_agent", name=name, func_name=func_name)


ROLE_FACTORY_NAMES: dict[str, str] = {
    "request_handler": "get_request_handler_agent",
    "mission_planner": "get_mission_planner_agent",
    "device_bridge": "get_device_bridge_agent",
    "insight_reporter": "get_insight_reporter_agent",
    "policy_manager": "get_policy_manager_agent",
    "system_sentinel": "get_system_sentinel_agent",
}


def resolve_agent_profile(role: str, model: str, **kwargs: Any):
    factory_name = ROLE_FACTORY_NAMES.get(role, role)
    factory = registry.get_agent(factory_name)
    if factory is None:
        return None
    return factory(model, **kwargs)


def load_agents_recursively(base_dir: str, base_package: str) -> None:
    for root, _dirs, files in os.walk(base_dir):
        rel_path = os.path.relpath(root, base_dir)
        for file in files:
            if not file.endswith(".py") or file.startswith("__"):
                continue
            if rel_path == ".":
                module_path = f"{base_package}.{file[:-3]}"
            else:
                module_path = f"{base_package}.{rel_path.replace(os.path.sep, '.')}.{file[:-3]}"
            try:
                importlib.import_module(module_path)
            except Exception as exc:
                print(f"Warning: Failed to import {module_path}: {exc}")
