from __future__ import annotations

"""시스템 이벤트/승인 입력 모델."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SystemEventInput(BaseModel):
    event_type: str
    source_id: str
    source_role: str = "unknown"
    severity: str = "info"
    summary: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    flow_id: Optional[str] = None
    causation_id: Optional[str] = None
    target_agent_id: Optional[str] = None
    target_role: Optional[str] = None
    requires_user_approval: bool = False
    auto_response: Optional[bool] = None


class ResponseApprovalInput(BaseModel):
    approved: bool = True
    notes: Optional[str] = None
