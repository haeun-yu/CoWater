from __future__ import annotations

# 02 에이전트의 입력 텔레메트리를 정리하고 계획 후보를 기록하는 Planner Layer다.

from dataclasses import dataclass, field
from typing import Any

from .models import AgentRecommendationRecord, DeviceAgentStateRecord, utc_now_iso


@dataclass
class PlanRecord:
    at: str
    token: str
    device_type: str | None
    llm_enabled: bool
    stream: str | None
    telemetry: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "token": self.token,
            "device_type": self.device_type,
            "llm_enabled": self.llm_enabled,
            "stream": self.stream,
            "telemetry": dict(self.telemetry),
            "candidates": list(self.candidates),
            "context": dict(self.context),
        }


class PlannerLayer:
    def plan(
        self,
        session: DeviceAgentStateRecord,
        envelope: dict[str, Any],
        payload: dict[str, Any],
        recommendations: list[AgentRecommendationRecord],
    ) -> PlanRecord:
        telemetry = {
            "device_id": envelope.get("device_id") or session.device_id,
            "device_name": envelope.get("device_name") or session.device_name,
            "device_type": envelope.get("device_type") or session.device_type,
            "stream": envelope.get("stream"),
            "position": payload.get("position"),
            "motion": payload.get("motion"),
            "sensor_keys": sorted(payload.get("sensors", {}).keys()) if isinstance(payload.get("sensors"), dict) else [],
        }
        plan = PlanRecord(
            at=utc_now_iso(),
            token=session.token,
            device_type=session.device_type,
            llm_enabled=session.llm_enabled,
            stream=str(envelope.get("stream") or session.last_stream or "telemetry"),
            telemetry=telemetry,
            candidates=[item.to_dict() for item in recommendations],
            context={
                "home_position": session.home_position,
                "registry_id": session.registry_id,
                "connected": session.connected,
            },
        )
        session.last_plan = plan.to_dict()
        session.context["planner"] = {
            "at": plan.at,
            "stream": plan.stream,
            "candidate_count": len(plan.candidates),
        }
        session.context["plan"] = plan.to_dict()
        session.remember(
            {
                "kind": "plan",
                "at": plan.at,
                "plan": plan.to_dict(),
            }
        )
        return plan
