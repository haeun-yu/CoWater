from __future__ import annotations

"""시스템 이벤트의 규칙/LLM 분석 계층."""

import json
from typing import Any, Optional
from uuid import uuid4

import httpx

from ..core.config import utc_now_iso


def llm_enabled(hub: Any) -> bool:
    """LLM 설정이 실제로 채워져 있는지 확인한다."""
    llm_cfg = hub.analysis_settings.get("llm") or {}
    provider = str(llm_cfg.get("provider") or "").strip()
    model = str(llm_cfg.get("model") or "").strip()
    return bool(provider and model)


def event_summary(payload: Any) -> str:
    """이벤트의 사람이 읽을 수 있는 요약 문장을 만든다."""
    if getattr(payload, "summary", None):
        return str(payload.summary).strip()
    return f"{payload.event_type} from {payload.source_id}"


def build_event_record(hub: Any, payload: Any) -> Any:
    """입력 이벤트를 내부 정규화 레코드로 변환한다."""
    from ..core.models import SystemEventRecord

    strategy = "hybrid" if llm_enabled(hub) else "rule"
    return SystemEventRecord(
        event_id=str(uuid4()),
        event_type=payload.event_type,
        source_id=payload.source_id,
        source_role=payload.source_role,
        severity=payload.severity,
        summary=event_summary(payload),
        payload=dict(payload.payload),
        flow_id=payload.flow_id,
        causation_id=payload.causation_id,
        decision_strategy=strategy,
        target_agent_id=payload.target_agent_id,
        route_mode=None,
        user_approval_required=bool(payload.requires_user_approval),
    )


def rule_analyze_event(hub: Any, event: Any) -> dict[str, Any]:
    """규칙 기반 분석을 수행한다."""
    payload = event.payload or {}
    lowered_type = event.event_type.lower()
    lowered_summary = (event.summary or "").lower()
    battery_percent = payload.get("battery_percent")
    if isinstance(battery_percent, (int, float)):
        battery_percent = float(battery_percent)
    else:
        power = payload.get("power") if isinstance(payload.get("power"), dict) else {}
        raw_battery = power.get("battery_percent")
        battery_percent = float(raw_battery) if isinstance(raw_battery, (int, float, str)) and str(raw_battery).strip() else None

    alert_type = "system_notice"
    severity = event.severity or "info"
    message = event.summary
    recommended_action: Optional[str] = None
    target_role: Optional[str] = event.source_role
    target_agent_id: Optional[str] = event.target_agent_id
    requires_user_approval = bool(event.user_approval_required)
    auto_response = bool(hub.analysis_settings.get("auto_response", True))
    route_mode = "direct"

    if "battery" in lowered_type or "battery" in lowered_summary:
        alert_type = "battery_low"
        message = f"{event.source_id} 배터리 상태 경고"
        if battery_percent is not None and battery_percent <= 10:
            recommended_action = "charge_at_tower"
            severity = "critical"
            target_role = target_role or "regional_orchestrator"
            auto_response = True
        elif battery_percent is not None and battery_percent <= 30:
            recommended_action = "alert_operator"
            severity = "warning"
            requires_user_approval = True
        else:
            recommended_action = "alert_operator"
    elif "light" in lowered_type or "dark" in lowered_summary or "low_light" in lowered_type:
        alert_type = "low_light"
        message = f"{event.source_id} 조도 부족 감지"
        if payload.get("light_enabled") is True or payload.get("led_light") in (True, "on"):
            recommended_action = "alert_operator"
            requires_user_approval = True
        else:
            recommended_action = "light_on"
            target_role = target_role or "rov"
    elif "target" in lowered_type or "contact" in lowered_type or "sonar" in lowered_type or "target" in lowered_summary:
        alert_type = "target_detected"
        message = f"{event.source_id}에서 타깃 감지"
        recommended_action = "alert_operator"
        requires_user_approval = True
    elif "route" in lowered_type or "deviation" in lowered_type or "off_route" in lowered_type:
        alert_type = "route_deviation"
        message = f"{event.source_id} 경로 이탈 감지"
        recommended_action = "alert_operator"
        requires_user_approval = True
    elif "offline" in lowered_type or "heartbeat" in lowered_type and payload.get("status") == "offline":
        alert_type = "agent_offline"
        message = f"{event.source_id} 응답 없음"
        recommended_action = "alert_operator"
        requires_user_approval = True
    elif event.event_type in {"user.command", "command.request"}:
        alert_type = "user_command"
        message = event.summary or "사용자 명령 수신"
        recommended_action = payload.get("command") or payload.get("action") or "review_command"
        auto_response = bool(payload.get("auto_response", False))
        requires_user_approval = not auto_response
    else:
        alert_type = "system_event"
        message = event.summary
        recommended_action = payload.get("suggested_action") or "alert_operator"
        requires_user_approval = True

    if recommended_action == "light_on" and target_role is None:
        target_role = "rov"
    if recommended_action == "charge_at_tower" and target_role is None:
        target_role = "regional_orchestrator"
    if recommended_action == "alert_operator":
        target_agent_id = target_agent_id or hub.state.parent_id or None

    if recommended_action in hub.analysis_settings.get("approval_required_actions", []):
        requires_user_approval = True

    return {
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "recommended_action": recommended_action,
        "target_role": target_role,
        "target_agent_id": target_agent_id,
        "route_mode": route_mode,
        "requires_user_approval": requires_user_approval,
        "auto_response": auto_response,
    }


async def llm_analyze_event(hub: Any, event: Any) -> Optional[dict[str, Any]]:
    """Ollama 계열 LLM이 설정되어 있으면 보조 판단을 요청한다."""
    llm_cfg = hub.analysis_settings.get("llm") or {}
    provider = str(llm_cfg.get("provider") or "").strip().lower()
    model = str(llm_cfg.get("model") or "").strip()
    base_url = str(llm_cfg.get("base_url") or "").rstrip("/")
    if provider != "ollama" or not model or not base_url:
        return None
    prompt = {
        "event": event.to_dict(),
        "instructions": {
            "output": "JSON only",
            "fields": [
                "alert_type",
                "severity",
                "message",
                "recommended_action",
                "target_role",
                "target_agent_id",
                "requires_user_approval",
                "auto_response",
                "route_mode",
                "reason",
            ],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Return a compact JSON object that helps decide the safest remediation for a system agent.",
                        },
                        {
                            "role": "user",
                            "content": json.dumps(prompt, ensure_ascii=False),
                        },
                    ],
                    "stream": False,
                    "options": {"temperature": llm_cfg.get("temperature", 0.2)},
                },
            )
            resp.raise_for_status()
            body = resp.json()
            content = (body.get("message") or {}).get("content") or ""
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
    except Exception as exc:
        hub.state.remember({"kind": "llm.analysis_failed", "at": utc_now_iso(), "error": str(exc), "event_id": event.event_id})
    return None


async def analyze_event(hub: Any, event: Any) -> dict[str, Any]:
    """이벤트를 분석해 알림 및 대응 권고를 만든다."""
    analysis = rule_analyze_event(hub, event)
    ambiguous = analysis.get("alert_type") in {"system_notice", "system_event"} or analysis.get("recommended_action") in {None, "alert_operator", "review_command"}
    if llm_enabled(hub) and ambiguous:
        llm_result = await llm_analyze_event(hub, event)
        if llm_result:
            for key in ("alert_type", "severity", "message", "recommended_action", "target_role", "target_agent_id", "requires_user_approval", "auto_response", "route_mode"):
                if key in llm_result and llm_result[key] is not None:
                    analysis[key] = llm_result[key]
            analysis["analysis_source"] = "hybrid"
            analysis["llm_reason"] = llm_result.get("reason")
        else:
            analysis["analysis_source"] = "rule"
    else:
        analysis["analysis_source"] = "rule"
    return analysis
