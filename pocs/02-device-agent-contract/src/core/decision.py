from __future__ import annotations

# 02 에이전트의 결정 결과와 선택 규칙을 담당하는 Decision Layer다.

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .models import AgentRecommendationRecord, DeviceAgentStateRecord, utc_now_iso
from .planner import PlanRecord


@dataclass
class DecisionRecord:
    strategy: str
    selected_action: str
    selected_reason: str
    selected_priority: str
    selected_params: dict[str, Any] = field(default_factory=dict)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    llm_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
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
        return {
            "action": self.selected_action,
            "reason": self.selected_reason,
            "priority": self.selected_priority,
            "params": dict(self.selected_params),
            "strategy": self.strategy,
        }


class DecisionLayer:
    _priority_rank = {"high": 0, "normal": 1, "low": 2}

    def strategy_for(self, session: DeviceAgentStateRecord) -> str:
        return "hybrid" if session.llm_enabled else "rule"

    def _ordered(self, recommendations: Iterable[AgentRecommendationRecord]) -> list[AgentRecommendationRecord]:
        return sorted(
            list(recommendations),
            key=lambda item: (self._priority_rank.get(item.priority, 1), item.action),
        )

    def decide(
        self,
        session: DeviceAgentStateRecord,
        plan: PlanRecord,
    ) -> Optional[DecisionRecord]:
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
            session.last_decision = None
            session.context["decision"] = None
            session.context["decision_strategy"] = self.strategy_for(session)
            return None

        ordered = self._ordered(recommendations)
        selected = ordered[0]
        decision = DecisionRecord(
            strategy=self.strategy_for(session),
            selected_action=selected.action,
            selected_reason=selected.reason,
            selected_priority=selected.priority,
            selected_params=dict(selected.params),
            candidates=[item.to_dict() for item in ordered],
            llm_enabled=session.llm_enabled,
        )
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
