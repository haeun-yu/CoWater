from __future__ import annotations

# 02 에이전트의 계획, 결정, 실행 결과를 모아서 세션 메모리로 남기는 Feedback Layer다.

from dataclasses import dataclass
from typing import Any, Optional

from .models import DeviceAgentStateRecord, utc_now_iso


@dataclass
class FeedbackRecord:
    at: str
    source: str
    status: str
    note: Optional[str] = None
    plan: Optional[dict[str, Any]] = None
    decision: Optional[dict[str, Any]] = None
    execution: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "source": self.source,
            "status": self.status,
            "note": self.note,
            "plan": self.plan,
            "decision": self.decision,
            "execution": self.execution,
        }


class FeedbackLayer:
    def record(
        self,
        session: DeviceAgentStateRecord,
        *,
        source: str,
        plan: dict[str, Any] | None = None,
        decision: dict[str, Any] | None = None,
        execution: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> FeedbackRecord:
        if execution is not None:
            status = "executed" if execution.get("delivered") else "failed"
        elif decision is not None:
            status = "planned"
        else:
            status = "idle"
        record = FeedbackRecord(
            at=utc_now_iso(),
            source=source,
            status=status,
            note=note,
            plan=plan,
            decision=decision,
            execution=execution,
        )
        session.last_feedback = record.to_dict()
        session.context["feedback"] = record.to_dict()
        session.remember(
            {
                "kind": "feedback",
                "at": record.at,
                "feedback": record.to_dict(),
            }
        )
        return record
