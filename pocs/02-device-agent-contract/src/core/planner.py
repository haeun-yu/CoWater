from __future__ import annotations

# 02 에이전트의 입력 텔레메트리를 정리하고 계획 후보를 기록하는 Planner Layer다.

from dataclasses import dataclass, field
from typing import Any

from .models import AgentRecommendationRecord, DeviceAgentStateRecord, utc_now_iso


@dataclass
class PlanRecord:
    # Planner가 telemetry를 어떤 판단 재료로 묶었는지 저장하는 스냅샷이다.
    at: str
    token: str
    device_type: str | None
    llm_enabled: bool
    stream: str | None
    telemetry: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # UI와 다음 레이어가 그대로 읽을 수 있도록 직렬화한다.
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
        # 1) telemetry와 envelope에서 판단에 필요한 최소 정보를 추린다.
        telemetry = {
            "device_id": envelope.get("device_id") or session.device_id,
            "device_name": envelope.get("device_name") or session.device_name,
            "device_type": envelope.get("device_type") or session.device_type,
            "stream": envelope.get("stream"),
            "position": payload.get("position"),
            "motion": payload.get("motion"),
            "power": payload.get("power"),
            "sensor_keys": sorted(payload.get("sensors", {}).keys()) if isinstance(payload.get("sensors"), dict) else [],
            "command_mode": payload.get("command", {}).get("mode") if isinstance(payload.get("command"), dict) else None,
        }

        # 2) 현재 세션 상태와 추천 후보를 묶어서 "plan" 객체로 만든다.
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

        # 3) 최신 plan은 세션의 현재 상태로 저장하고, context와 memory에도 남긴다.
        session.last_plan = plan.to_dict()
        session.context["planner"] = {
            "at": plan.at,
            "stream": plan.stream,
            "candidate_count": len(plan.candidates),
        }
        session.context["plan"] = plan.to_dict()

        # 4) 이 기록은 나중에 decision/execution/feedback 흐름을 추적하는 기준이 된다.
        session.remember(
            {
                "kind": "plan",
                "at": plan.at,
                "plan": plan.to_dict(),
            }
        )
        return plan
