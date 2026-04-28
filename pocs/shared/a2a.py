"""
Agent-to-Agent (A2A) 통신 모듈

모든 Agent (POC 01-05)가 A2A를 통해 상호 통신:
- Supervisor → Middle/Lower agents: 명령 전달
- Middle agents → Lower agents: 분해된 작업 할당
- Lower agents → Upper agents: 상태/결과 보고
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> str:
    """UTC 현재 시간을 ISO format으로 반환"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class A2APart(BaseModel):
    type: str  # "text" | "data"
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
    """메시지에서 data 또는 text 추출"""
    for part in message.parts:
        if part.type == "data" and isinstance(part.data, dict):
            return part.data
    for part in message.parts:
        if part.type == "text" and part.text:
            return {"text": part.text}
    return {}


def build_task(task_id: str | None, message: A2AMessage, result: dict[str, Any]) -> dict[str, Any]:
    """Task 객체 생성"""
    now = utc_now()
    return {
        "id": task_id or str(uuid4()),
        "status": {"state": "completed"},
        "createdAt": now,
        "updatedAt": now,
        "message": message.model_dump(),
        "artifacts": [{"name": "result", "parts": [{"type": "data", "data": result}]}],
    }
