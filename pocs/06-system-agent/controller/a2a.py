from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from agent.state import utc_now


class A2APart(BaseModel):
    type: str
    text: Optional[str] = None
    data: Optional[dict[str, Any]] = None


class A2AMessage(BaseModel):
    role: str = "user"
    parts: list[A2APart] = Field(default_factory=list)


class A2ASendRequest(BaseModel):
    message: A2AMessage
    taskId: Optional[str] = None
    contextId: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def extract_message_data(message: A2AMessage) -> dict[str, Any]:
    for part in message.parts:
        if part.type == "data" and isinstance(part.data, dict):
            return part.data
    for part in message.parts:
        if part.type == "text" and part.text:
            return {"text": part.text}
    return {}


def build_task(task_id: str | None, message: A2AMessage, result: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    return {
        "id": task_id or str(uuid4()),
        "status": {"state": "completed"},
        "createdAt": now,
        "updatedAt": now,
        "message": message.model_dump(),
        "artifacts": [{"name": "result", "parts": [{"type": "data", "data": result}]}],
    }

