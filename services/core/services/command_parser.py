from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class ParsedCommand:
    intent: str
    summary: str
    required_role: str
    target_type: str
    target_id: str
    arguments: dict


_AGENT_ALIAS_MAP = {
    "cpa": "cpa-agent",
    "cpa-agent": "cpa-agent",
    "충돌": "cpa-agent",
    "충돌위험": "cpa-agent",
    "충돌위험감지": "cpa-agent",
    "zone": "zone-monitor",
    "zone-monitor": "zone-monitor",
    "구역": "zone-monitor",
    "구역감시": "zone-monitor",
    "구역침입": "zone-monitor",
    "anomaly": "anomaly-rule",
    "anomaly-rule": "anomaly-rule",
    "이상": "anomaly-rule",
    "이상행동": "anomaly-rule",
    "anomaly-ai": "anomaly-ai",
    "이상분석": "anomaly-ai",
    "ai이상분석": "anomaly-ai",
    "distress": "distress-agent",
    "distress-agent": "distress-agent",
    "조난": "distress-agent",
    "report": "report-agent",
    "report-agent": "report-agent",
    "리포트": "report-agent",
    "보고서": "report-agent",
    "chat": "chat-agent",
    "chat-agent": "chat-agent",
    "보좌관": "chat-agent",
    "assistant": "chat-agent",
}

_ALERT_ACTION_ALIAS_MAP = {
    "ack": "acknowledge",
    "acknowledge": "acknowledge",
    "인지": "acknowledge",
    "확인": "acknowledge",
    "resolve": "resolve",
    "해결": "resolve",
    "종료": "resolve",
    "start_investigation": "start_investigation",
    "investigate": "start_investigation",
    "조사": "start_investigation",
    "조사시작": "start_investigation",
    "escalate": "escalate",
    "에스컬레이션": "escalate",
    "notify_guard": "notify_guard",
    "경비정알림": "notify_guard",
    "request_course_change": "request_course_change",
    "변침요청": "request_course_change",
    "request_speed_reduction": "request_speed_reduction",
    "감속요청": "request_speed_reduction",
    "request_zone_exit": "request_zone_exit",
    "구역이탈요청": "request_zone_exit",
}

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _normalize_token(value: str) -> str:
    return re.sub(r"[\s_]+", "", value.strip().lower())


def _normalize_level(raw: str) -> str:
    compact = raw.strip().upper()
    if compact in {"1", "2", "3"}:
        return f"L{compact}"
    if compact in {"L1", "L2", "L3"}:
        return compact
    raise HTTPException(400, f"Unsupported level: {raw}")


def _resolve_agent_id(raw: str) -> str:
    normalized = _normalize_token(raw)
    agent_id = _AGENT_ALIAS_MAP.get(normalized)
    if agent_id is None:
        raise HTTPException(400, f"Unsupported agent target: {raw}")
    return agent_id


def _resolve_alert_action(raw: str) -> str:
    normalized = _normalize_token(raw)
    action = _ALERT_ACTION_ALIAS_MAP.get(normalized)
    if action is None:
        raise HTTPException(400, f"Unsupported alert action: {raw}")
    return action


def _require_alert_id(value: str) -> str:
    alert_id = value.strip()
    if not _UUID_RE.match(alert_id):
        raise HTTPException(400, "Alert commands require an explicit alert UUID")
    return alert_id


def parse_command(text: str) -> ParsedCommand:
    raw = text.strip()
    if not raw:
        raise HTTPException(400, "Command text is required")

    compact = re.sub(r"\s+", " ", raw)

    structured_patterns = [
        (
            re.compile(r"^agent\s+enable\s+(.+)$", re.IGNORECASE),
            lambda m: ParsedCommand(
                intent="agent.enable",
                summary=f"Enable agent {_resolve_agent_id(m.group(1))}",
                required_role="admin",
                target_type="agent",
                target_id=_resolve_agent_id(m.group(1)),
                arguments={},
            ),
        ),
        (
            re.compile(r"^agent\s+disable\s+(.+)$", re.IGNORECASE),
            lambda m: ParsedCommand(
                intent="agent.disable",
                summary=f"Disable agent {_resolve_agent_id(m.group(1))}",
                required_role="admin",
                target_type="agent",
                target_id=_resolve_agent_id(m.group(1)),
                arguments={},
            ),
        ),
        (
            re.compile(r"^agent\s+level\s+(.+?)\s+(L?[123])$", re.IGNORECASE),
            lambda m: ParsedCommand(
                intent="agent.set_level",
                summary=f"Set agent {_resolve_agent_id(m.group(1))} level to {_normalize_level(m.group(2))}",
                required_role="admin",
                target_type="agent",
                target_id=_resolve_agent_id(m.group(1)),
                arguments={"level": _normalize_level(m.group(2))},
            ),
        ),
        (
            re.compile(r"^agent\s+run\s+(.+?)(?:\s+platform\s+(.+))?$", re.IGNORECASE),
            lambda m: ParsedCommand(
                intent="agent.run",
                summary=f"Run agent {_resolve_agent_id(m.group(1))}",
                required_role="operator",
                target_type="agent",
                target_id=_resolve_agent_id(m.group(1)),
                arguments={"platform_id": m.group(2).strip() if m.group(2) else None},
            ),
        ),
        (
            re.compile(r"^alert\s+ack(?:nowledge)?\s+(.+)$", re.IGNORECASE),
            lambda m: ParsedCommand(
                intent="alert.acknowledge",
                summary=f"Acknowledge alert {_require_alert_id(m.group(1))}",
                required_role="operator",
                target_type="alert",
                target_id=_require_alert_id(m.group(1)),
                arguments={"action": "acknowledge"},
            ),
        ),
        (
            re.compile(r"^alert\s+resolve\s+(.+)$", re.IGNORECASE),
            lambda m: ParsedCommand(
                intent="alert.resolve",
                summary=f"Resolve alert {_require_alert_id(m.group(1))}",
                required_role="operator",
                target_type="alert",
                target_id=_require_alert_id(m.group(1)),
                arguments={"action": "resolve"},
            ),
        ),
        (
            re.compile(r"^alert\s+action\s+(.+?)\s+(.+)$", re.IGNORECASE),
            lambda m: ParsedCommand(
                intent="alert.action",
                summary=f"Execute alert action {_resolve_alert_action(m.group(2))} on {_require_alert_id(m.group(1))}",
                required_role="operator",
                target_type="alert",
                target_id=_require_alert_id(m.group(1)),
                arguments={"action": _resolve_alert_action(m.group(2))},
            ),
        ),
    ]

    for pattern, builder in structured_patterns:
        match = pattern.match(compact)
        if match:
            return builder(match)

    natural_patterns = [
        (
            re.compile(r"^(.+?)\s*(?:에이전트)?\s*(?:켜줘|켜|활성화)$", re.IGNORECASE),
            "agent.enable",
        ),
        (
            re.compile(
                r"^(.+?)\s*(?:에이전트)?\s*(?:꺼줘|꺼|비활성화)$", re.IGNORECASE
            ),
            "agent.disable",
        ),
        (
            re.compile(
                r"^(.+?)\s*(?:에이전트|agent)?\s*(?:레벨|level)\s*(L?[123])(?:로)?\s*(?:변경해줘|변경|설정해줘|설정)?$",
                re.IGNORECASE,
            ),
            "agent.set_level",
        ),
        (
            re.compile(r"^(.+?)\s*(?:에이전트)?\s*(?:실행해줘|실행)$", re.IGNORECASE),
            "agent.run",
        ),
        (
            re.compile(r"^경보\s+(.+?)\s*(?:인지|확인|acknowledge)$", re.IGNORECASE),
            "alert.acknowledge",
        ),
        (
            re.compile(r"^경보\s+(.+?)\s*(?:해결|종료|resolve)$", re.IGNORECASE),
            "alert.resolve",
        ),
    ]

    for pattern, intent in natural_patterns:
        match = pattern.match(compact)
        if not match:
            continue
        if intent == "agent.enable":
            agent_id = _resolve_agent_id(match.group(1))
            return ParsedCommand(
                intent=intent,
                summary=f"Enable agent {agent_id}",
                required_role="admin",
                target_type="agent",
                target_id=agent_id,
                arguments={},
            )
        if intent == "agent.disable":
            agent_id = _resolve_agent_id(match.group(1))
            return ParsedCommand(
                intent=intent,
                summary=f"Disable agent {agent_id}",
                required_role="admin",
                target_type="agent",
                target_id=agent_id,
                arguments={},
            )
        if intent == "agent.set_level":
            agent_id = _resolve_agent_id(match.group(1))
            level = _normalize_level(match.group(2))
            return ParsedCommand(
                intent=intent,
                summary=f"Set agent {agent_id} level to {level}",
                required_role="admin",
                target_type="agent",
                target_id=agent_id,
                arguments={"level": level},
            )
        if intent == "agent.run":
            agent_id = _resolve_agent_id(match.group(1))
            return ParsedCommand(
                intent=intent,
                summary=f"Run agent {agent_id}",
                required_role="operator",
                target_type="agent",
                target_id=agent_id,
                arguments={"platform_id": None},
            )
        if intent == "alert.acknowledge":
            alert_id = _require_alert_id(match.group(1))
            return ParsedCommand(
                intent=intent,
                summary=f"Acknowledge alert {alert_id}",
                required_role="operator",
                target_type="alert",
                target_id=alert_id,
                arguments={"action": "acknowledge"},
            )
        if intent == "alert.resolve":
            alert_id = _require_alert_id(match.group(1))
            return ParsedCommand(
                intent=intent,
                summary=f"Resolve alert {alert_id}",
                required_role="operator",
                target_type="alert",
                target_id=alert_id,
                arguments={"action": "resolve"},
            )

    raise HTTPException(
        400,
        "Unsupported command. Try commands like 'agent enable cpa', 'agent level cpa L2', or 'alert resolve <uuid>'.",
    )
