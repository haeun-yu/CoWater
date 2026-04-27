from __future__ import annotations

# 02 에이전트의 결정 결과와 선택 규칙을 담당하는 Decision Layer다.

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import AgentRecommendationRecord, DeviceAgentStateRecord, utc_now_iso
from .planner import PlanRecord


@dataclass
class DecisionRecord:
    # Planner가 만든 후보들 중 최종으로 무엇을 선택했는지 기록한다.
    strategy: str
    selected_action: str
    selected_reason: str
    selected_priority: str
    selected_params: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    llm_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        # UI와 feedback 레이어가 읽기 쉽게 직렬화한다.
        return {
            "strategy": self.strategy,
            "selected_action": self.selected_action,
            "selected_reason": self.selected_reason,
            "selected_priority": self.selected_priority,
            "selected_params": dict(self.selected_params),
            "candidates": list(self.candidates),
            "llm_enabled": self.llm_enabled,
        }

    def to_command(self) -> dict[str, Any]:
        # execution 레이어가 바로 보낼 수 있는 command 형태로 바꾼다.
        return {
            "action": self.selected_action,
            "reason": self.selected_reason,
            "priority": self.selected_priority,
            "params": dict(self.selected_params),
            "strategy": self.strategy,
        }


class DecisionLayer:
    _priority_rank = {"high": 0, "normal": 1, "low": 2}
    _action_rank = {
        "charge_at_tower": 0,
        "surface": 1,
        "slow_down": 2,
        "light_on": 3,
        "hold_depth": 4,
        "hold_position": 5,
        "move_to_device": 6,
        "follow_target": 7,
        "return_to_base": 8,
        "alert_operator": 99,
    }

    def strategy_for(self, session: DeviceAgentStateRecord) -> str:
        # LLM 설정이 있으면 hybrid, 없으면 rule 기반으로 본다.
        return "hybrid" if session.llm_enabled else "rule"

    def _ordered(self, recommendations: Iterable[AgentRecommendationRecord]) -> list[AgentRecommendationRecord]:
        # 안전 동작을 앞세우기 위해 priority와 action 순서를 함께 고려한다.
        return sorted(
            list(recommendations),
            key=lambda item: (
                self._priority_rank.get(item.priority, 1),
                self._action_rank.get(item.action, 50),
                item.action,
            ),
        )

    def decide(
        self,
        session: DeviceAgentStateRecord,
        plan: PlanRecord,
    ) -> Optional[DecisionRecord]:
        # 1) planner가 만든 후보들을 다시 AgentRecommendationRecord로 복원한다.
        recommendations = [
            AgentRecommendationRecord(
                action=item.get("action", ""),
                reason=item.get("reason", ""),
                priority=item.get("priority", "normal"),
                params=dict(item.get("params") or {}),
            )
            for item in plan.candidates
            if isinstance(item, dict) and item.get("action")
        ]
        if not recommendations:
            # 후보가 없으면 이번 턴의 결정도 없다고 기록한다.
            session.last_decision = None
            session.context["decision"] = None
            session.context["decision_strategy"] = self.strategy_for(session)
            return None

        # 2) 우선순위와 안전 행동 순서에 따라 후보를 정렬한다.
        ordered = self._ordered(recommendations)
        selected = ordered[0]

        # 3) 최종 선택된 action과 이유를 DecisionRecord에 담는다.
        decision = DecisionRecord(
            strategy=self.strategy_for(session),
            selected_action=selected.action,
            selected_reason=selected.reason,
            selected_priority=selected.priority,
            selected_params=dict(selected.params),
            candidates=[item.to_dict() for item in ordered],
            llm_enabled=session.llm_enabled,
        )

        # 4) 최신 결정은 세션 상태와 context, memory에 저장한다.
        session.last_decision = decision.to_dict()
        session.context["decision_strategy"] = decision.strategy
        session.context["decision"] = decision.to_dict()
        session.remember(
            {
                "kind": "decision",
                "at": utc_now_iso(),
                "decision": decision.to_dict(),
            }
        )
        return decision
