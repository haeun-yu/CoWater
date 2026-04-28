"""
Agent Command 모델 - 모든 Agent에서 사용

A2A를 통해 전달되는 command의 표준 형식
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    """Agent가 받는 command 요청"""
    action: str  # "navigate_to", "dive_and_scan", "remove_mine" 등
    reason: Optional[str] = None
    priority: str = "normal"  # "normal" | "urgent" | "low"
    params: dict[str, Any] = Field(default_factory=dict)


class CommandResult(BaseModel):
    """Command 실행 결과"""
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
