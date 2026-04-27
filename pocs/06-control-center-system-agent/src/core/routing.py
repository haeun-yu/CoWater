from __future__ import annotations

"""미션 배분과 A2A/command 라우팅."""

from typing import Any, Optional
from uuid import uuid4

from ..core.config import utc_now_iso
from ..transport.a2a import post_json, send_a2a_message


def build_message_record(hub: Any, payload: Any, routed_via: Optional[str] = None, status_text: str = "received") -> Any:
    from ..core.models import MessageRecord

    return MessageRecord(
        message_id=payload.message_id or str(uuid4()),
        message_type=payload.message_type,
        from_agent_id=payload.from_agent_id,
        to_agent_id=payload.to_agent_id,
        task_id=payload.task_id,
        conversation_id=payload.conversation_id,
        role=payload.role,
        scope=payload.scope,
        priority=payload.priority,
        ttl=payload.ttl,
        payload=payload.payload,
        route_hint=payload.route_hint,
        received_at=utc_now_iso(),
        routed_via=routed_via,
        status=status_text,
    )


def make_task_assign_message(hub: Any, event: Any, alert: Any, response: Any, target: Any, analysis: dict[str, Any], route_mode: str) -> Any:
    from ..core.models import A2AMessageInput

    return A2AMessageInput(
        message_type="task.assign",
        message_id=str(uuid4()),
        conversation_id=event.flow_id,
        task_id=response.task_id,
        from_agent_id=hub.state.agent_id,
        to_agent_id=target.agent_id,
        role=target.role,
        scope=event.source_role,
        priority="high" if event.severity in {"warning", "critical"} else "normal",
        payload={
            "event": event.to_dict(),
            "alert": alert.to_dict(),
            "response": response.to_dict(),
            "command": {
                "action": event.recommended_action,
                "reason": response.reason,
                "target_role": analysis.get("target_role") or target.role,
            },
        },
        route_hint={"preferred_route": route_mode},
    )
