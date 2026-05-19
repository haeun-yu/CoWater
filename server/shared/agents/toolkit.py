from __future__ import annotations

from typing import Any, Callable

from .types import Agent, Result


def make_tool(
    name: str,
    description: str,
    *,
    role: str,
    endpoint: str | None = None,
    action: str | None = None,
    method: str = "POST",
) -> Callable[..., dict[str, Any]]:
    def _tool(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool": name,
            "role": role,
            "description": description,
            "method": method,
        }
        if endpoint is not None:
            payload["endpoint"] = endpoint
        if action is not None:
            payload["action"] = action
        if args:
            payload["args"] = list(args)
        if kwargs:
            payload["parameters"] = kwargs
        return payload

    _tool.__name__ = name
    _tool.__doc__ = description
    return _tool


def make_transfer_tool(
    name: str,
    description: str,
    target: Agent | Callable[[], Agent],
) -> Callable[[str], Result]:
    def _tool(sub_task_description: str) -> Result:
        target_agent = target() if callable(target) else target
        return Result(value=sub_task_description, agent=target_agent)

    _tool.__name__ = name
    _tool.__doc__ = description
    return _tool
