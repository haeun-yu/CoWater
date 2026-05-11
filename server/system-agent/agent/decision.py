"""
System Agent 의사결정 엔진 (LLM-primary)

- Critical 긴급(distress, collision_risk CRITICAL): 즉각 rule 대응, LLM 없음
- 그 외 모든 alert / 사용자 명령: LLM이 fleet 전체 컨텍스트를 보고 판단
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from agent.state import AgentState, utc_now
from skills.catalog import SkillCatalog

try:
    from agent.llm_client import make_llm_client, LLMErrorType, LLMErrorContext
except ImportError:
    make_llm_client = None
    LLMErrorType = None
    LLMErrorContext = None

logger = logging.getLogger(__name__)


# 생명 안전 — LLM 없이 즉각 에스컬레이션
CRITICAL_URGENT = {"distress", "collision_risk"}


class DecisionEngine:
    def __init__(self, agent_config: dict[str, Any], skills: SkillCatalog) -> None:
        self.agent_config = agent_config
        self.skills = skills
        if not make_llm_client:
            raise RuntimeError("LLM client factory is unavailable")
        try:
            self.llm_client = make_llm_client(agent_config.get("llm", {}))
        except Exception as e:
            raise RuntimeError(f"System Agent LLM 초기화 실패: {e}") from e
        self.llm_enabled = True

    # ──────────────────────────────────────────────
    # Critical rule (즉각 대응)
    # ──────────────────────────────────────────────

    def is_critical_urgent(self, alert: dict[str, Any]) -> bool:
        alert_type = str(alert.get("alert_type") or "").lower()
        severity = str(alert.get("severity") or "").upper()
        return severity == "CRITICAL" and alert_type in CRITICAL_URGENT

    def critical_response(self, alert: dict[str, Any]) -> dict[str, Any]:
        alert_type = str(alert.get("alert_type") or "unknown")
        decision = {
            "at": utc_now(),
            "mode": "critical_rule",
            "action": "escalate_alert",
            "priority": "critical",
            "reasoning": f"{alert_type} CRITICAL — 즉각 에스컬레이션",
            "llm_analysis": None,
        }
        return decision

    def _normalize_llm_error(self, error_ctx: Any) -> dict[str, Any]:
        if error_ctx is None:
            return {}
        if hasattr(error_ctx, "to_dict"):
            try:
                return dict(error_ctx.to_dict())
            except Exception:
                pass
        if isinstance(error_ctx, dict):
            return dict(error_ctx)
        return {
            "error_type": "unknown_error",
            "message": str(error_ctx),
        }

    # ──────────────────────────────────────────────
    # 동기 decide (alert 기록용, 하위 호환)
    # ──────────────────────────────────────────────

    def decide(self, state: AgentState, alert: dict[str, Any]) -> dict[str, Any]:
        actions = set(self.skills.list_actions())
        alert_type = str(alert.get("alert_type") or "unknown")
        severity = str(alert.get("severity") or "INFORMATION").upper()
        metadata = alert.get("metadata") or {}
        recommendations: list[dict[str, Any]] = []

        if alert_type == "mine_detection" and "mission.assign" in actions:
            recommendations.append({
                "action": "mission.assign",
                "priority": "critical" if severity == "CRITICAL" else "high",
                "mission_type": "mine_survey_and_removal",
                "params": {"location": metadata.get("location", {})},
            })
        elif alert.get("recommended_action") and "task.assign" in actions:
            recommended = str(alert["recommended_action"]).lower()
            task_type = (
                "survey_depth" if "survey" in recommended
                else "remove_mine" if "remove" in recommended
                else "generic"
            )
            recommendations.append({
                "action": "task.assign",
                "priority": severity,
                "task_type": task_type,
                "params": {"location": metadata.get("location", {})},
            })

        decision = {
            "at": utc_now(),
            "mode": "rule",
            "recommendations": recommendations,
            "alert_type": alert_type,
            "severity": severity,
        }
        state.last_decision = decision
        return decision

    # ──────────────────────────────────────────────
    # LLM 분석
    # ──────────────────────────────────────────────

    async def analyze_alert(
        self,
        alert: dict[str, Any],
        devices: list[dict[str, Any]],
        state: AgentState,
    ) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        """
        Fleet 전체 컨텍스트로 alert 분석 → 디바이스 선정 / 임무 계획
        
        Returns: (llm_result, error_context)
        - If successful: (result_dict, None)
        - If failed: (None, error_dict)
        """
        try:
            prompt = self._alert_prompt(alert, devices, state)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)
            
            # LLM 오류 처리
            if error_ctx is not None:
                error_dict = self._normalize_llm_error(error_ctx)
                error_type = str(error_dict.get("error_type") or "unknown_error")
                log_fn = logger.warning if error_type == "circuit_open" else logger.error
                log_fn(
                    f"LLM alert 분석 실패 [{error_type}] "
                    f"(시도 {error_dict.get('attempt_number', 1)}/{error_dict.get('max_attempts', 3)}, "
                    f"{error_dict.get('elapsed_ms', 0)}ms): {error_dict.get('message', '')}"
                )
                return None, error_dict
            
            # 응답 파싱
            result = self._parse(response) if response else None
            if result:
                logger.info(f"LLM alert 분석 성공: {result.get('reasoning', '')[:80]}")
            else:
                logger.warning(f"LLM alert 분석 응답 파싱 실패 (응답: {response[:100] if response else 'empty'})")
            
            return result, None
            
        except Exception as e:
            logger.error(f"LLM alert 분석 중 예기치 않은 오류: {type(e).__name__}: {e}")
            error_dict = {
                "error_type": "unknown_error",
                "message": str(e),
                "recovery_strategy": "fallback",
            }
            return None, error_dict

    async def analyze_command(
        self,
        command: dict[str, Any],
        devices: list[dict[str, Any]],
        state: AgentState,
    ) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        """
        사용자 명령을 Fleet 컨텍스트로 해석 → 실행할 action 결정
        
        Returns: (llm_result, error_context)
        - If successful: (result_dict, None)
        - If failed: (None, error_dict)
        """
        try:
            prompt = self._command_prompt(command, devices, state)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)
            
            # LLM 오류 처리
            if error_ctx is not None:
                error_dict = self._normalize_llm_error(error_ctx)
                error_type = str(error_dict.get("error_type") or "unknown_error")
                log_fn = logger.warning if error_type == "circuit_open" else logger.error
                log_fn(
                    f"LLM 명령 해석 실패 [{error_type}] "
                    f"(시도 {error_dict.get('attempt_number', 1)}/{error_dict.get('max_attempts', 3)}, "
                    f"{error_dict.get('elapsed_ms', 0)}ms): {error_dict.get('message', '')}"
                )
                return None, error_dict
            
            # 응답 파싱
            result = self._parse(response) if response else None
            if result:
                logger.info(f"LLM 명령 해석 성공: {result.get('reasoning', '')[:80]}")
            else:
                logger.warning(f"LLM 명령 해석 응답 파싱 실패 (응답: {response[:100] if response else 'empty'})")
            
            return result, None
            
        except Exception as e:
            logger.error(f"LLM 명령 해석 중 예기치 않은 오류: {type(e).__name__}: {e}")
            error_dict = {
                "error_type": "unknown_error",
                "message": str(e),
                "recovery_strategy": "fallback",
            }
            return None, error_dict

    # ── alert type semantics ──────────────────────
    _ALERT_CONTEXT = {
        "mine_detection":     "수중 기뢰 또는 위험 물체 탐지. AUV로 정밀 탐색 후 ROV로 제거.",
        "battery_emergency":  "디바이스 배터리 위급. 해당 디바이스가 귀환 중이며 fleet 재조율 필요.",
        "collision_risk":     "충돌 위험 감지. 해당 디바이스 경보 확인 후 인근 지원 고려.",
        "distress":           "조난 신호. 즉각 에스컬레이션 및 인근 가용 자산 집결.",
        "battery_low":        "배터리 경고. 해당 디바이스 귀환 유도 또는 임무 재배분.",
        "communication_loss": "통신 두절. 인근 중계 디바이스 배치 또는 시스템 경보.",
        "tether_warning":     "ROV 테더 장력 이상. 즉시 확인 및 안전 조치.",
    }

    # ── action semantics ──────────────────────────
    _ACTION_DESC = {
        "mission.plan":    "임무 계획 수립 (params: mission_type, location)",
        "mission.assign":  "디바이스에 전체 임무 배정 (mine_detection 등 복합 임무)",
        "task.assign":     "단일 작업 배정 (params: action, location, target_device_id)",
        "approve_response":"시스템 대응 승인 및 실행 지시",
        "route_direct":    "디바이스에 직접 명령 전달 (중간 계층 없이)",
        "route_via_middle":"중간 계층 에이전트를 통해 명령 전달",
        "escalate_alert":  "운용자에게 경보 에스컬레이션 (자동 대응 불가 시)",
    }

    # ── device selection criteria ─────────────────
    _SELECTION_GUIDE = """\
디바이스 선정 기준 (중요도 순):
  1. 연결 상태: 온라인이고 예약되지 않은 디바이스만 선정
  2. 능력: 해당 임무를 수행할 수 있는 타입이어야 함
     - 탐색(survey_depth): AUV (소나 스캔)
     - 제거(remove_mine): ROV (매니퓰레이터)
  3. 배터리: 임무 후 귀환 여유 포함하여 30% 이상 권장
     (긴급 상황은 배터리 불문 최근접 배치)
  4. 거리: 위협 위치와 가까울수록 우선
  5. 복수 임무 필요 시 배터리가 높은 디바이스를 우선 배정하여 fleet 소진 방지"""

    # ──────────────────────────────────────────────
    # Prompt builders
    # ──────────────────────────────────────────────

    def _alert_prompt(
        self,
        alert: dict[str, Any],
        devices: list[dict[str, Any]],
        state: AgentState,
    ) -> str:
        actions = list(self.skills.list_actions())
        metadata = alert.get("metadata") or {}
        alert_type = str(alert.get("alert_type") or "unknown")
        alert_ctx = self._ALERT_CONTEXT.get(alert_type, "알 수 없는 이벤트. 상황을 판단하여 대응하세요.")

        action_lines = "\n".join(
            f"  - {a}: {self._ACTION_DESC.get(a, '(설명 없음)')}"
            for a in actions
        )

        return f"""당신은 CoWater 해양 통합 운용 플랫폼의 AI 지휘관입니다.
함대 전체를 관제하며, 수신된 alert에 대해 최적의 대응 action을 결정합니다.

## 수신된 Alert
- 유형: {alert_type}
- 의미: {alert_ctx}
- 심각도: {alert.get("severity", "INFORMATION")}
- 메시지: {alert.get("message", "")}
- 발생 위치: {json.dumps(metadata.get("location", {}), ensure_ascii=False)}

## 현재 Fleet 상태
{self._fleet_summary(devices)}

## 현재 진행 중인 임무 수: {len(state.tasks)}개

## 수행 가능한 action
{action_lines}

## 디바이스 선정 기준
{self._SELECTION_GUIDE}

## Action 선택 규칙
- mine_detection → 반드시 "mission.assign" (탐색 + 제거 복합 임무)
- 단일 작업 배정 → "task.assign"
- 자동 대응 불가 → "escalate_alert"

위 기준으로 최적의 action과 투입 디바이스를 결정하세요.
JSON 형식으로만 응답하세요. 설명 없이 JSON만:
{{
  "action": "<위 목록 중 하나>",
  "preferred_survey_device_id": "<탐색 담당 device id 또는 null>",
  "preferred_remove_device_id": "<제거 담당 device id 또는 null>",
  "priority": "critical" | "high" | "normal",
  "reasoning": "<선정 근거 — 배터리·거리·능력 중 어떤 기준이 결정적이었나>"
}}"""

    def _command_prompt(
        self,
        command: dict[str, Any],
        devices: list[dict[str, Any]],
        state: AgentState,
    ) -> str:
        actions = list(self.skills.list_actions())
        action_lines = "\n".join(
            f"  - {a}: {self._ACTION_DESC.get(a, '(설명 없음)')}"
            for a in actions
        )

        return f"""당신은 CoWater 해양 통합 운용 플랫폼의 AI 지휘관입니다.
운용자의 명령을 해석하고, 현재 fleet 상태에 맞는 실행 action을 결정합니다.

## 운용자 명령
{json.dumps(command, ensure_ascii=False)}

명령 해석 지침:
- action 필드가 명확하면 그대로 사용
- 자연어 reason/params에 대상 디바이스 이름이 있으면 fleet에서 찾아 id 매핑
- 대상이 불명확하면 임무 수행 가능한 디바이스 중 배터리가 가장 높은 것 선택
- 명령이 현재 fleet 상태상 불가능하면 action을 "escalate_alert"로 설정하고 reasoning에 이유 기술

## 현재 Fleet 상태
{self._fleet_summary(devices)}

## 수행 가능한 action
{action_lines}

JSON 형식으로만 응답하세요. 설명 없이 JSON만:
{{
  "action": "<위 목록 중 하나>",
  "target_device_id": "<대상 device id 또는 null>",
  "params": {{}},
  "reasoning": "<명령 해석 근거 및 디바이스 선정 이유>"
}}"""

    @staticmethod
    def _fmt_device(d: dict[str, Any], *, indent: str = "  ") -> str:
        agent = d.get("agent") or {}
        bat   = d.get("last_battery_percent")
        lat, lon = d.get("latitude"), d.get("longitude")
        avail = (agent.get("available_actions") or [])[:4]
        status = "온라인" if d.get("connected") else "오프라인"
        dtype = d.get("device_type", "?")
        name  = d.get("name", "?")

        # 특수 상태 표시
        flags: list[str] = []
        if d.get("is_submerged"):
            flags.append("수중잠항")
        if d.get("force_parent_routing"):
            flags.append("유선연결")
        conn_type = d.get("connectivity", "")
        if conn_type == "acoustic":
            flags.append("음향통신")

        line = f"{indent}[{d.get('id')}] {name} ({dtype}): {status}"
        if bat is not None:
            warn = " ⚠저배터리" if float(bat) < 30 else ""
            line += f", 배터리 {float(bat):.0f}%{warn}"
        if lat and lon:
            line += f", 위치({float(lat):.4f},{float(lon):.4f})"
        if flags:
            line += f", [{'/'.join(flags)}]"
        if avail:
            line += f", 가능action:{avail}"
        return line

    def _fleet_summary(self, devices: list[dict[str, Any]]) -> str:
        """
        Registry 데이터의 parent_id 필드로 실제 계층 구조를 구성합니다.
        parent_id는 내부 numeric id이며, devices는 내부 id 오름차순으로 정렬됩니다.
        위치 기반 휴리스틱으로 middle agent와 children을 매핑합니다.
        """
        middles = [d for d in devices if str(d.get("layer") or "") == "middle"]
        lowers  = [d for d in devices if str(d.get("layer") or "") == "lower"]

        def registry_id_of(device: dict[str, Any]) -> int | None:
            raw = device.get("registry_id")
            if raw is None:
                raw = device.get("id")
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        # middle 디바이스를 Registry numeric id로 직접 조회
        id_to_middle: dict[int, dict[str, Any]] = {
            rid: d
            for d in middles
            if (rid := registry_id_of(d)) is not None
        }
        middles_sorted = sorted(middles, key=lambda d: d.get("created_at") or "")

        # children 그룹화
        children_of: dict[str, list[dict[str, Any]]] = {}  # middle id → children
        direct: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []

        for d in lowers:
            pid = d.get("parent_id")
            if pid is None:
                direct.append(d)
            else:
                parent = id_to_middle.get(int(pid))
                if parent:
                    mid = str(registry_id_of(parent) or parent.get("id") or "")
                    children_of.setdefault(mid, []).append(d)
                else:
                    unmatched.append(d)

        parts: list[str] = []

        # 중계 계층
        if middles_sorted:
            parts.append("─── 중계 계층 (middle) ───")
            for m in middles_sorted:
                parts.append(self._fmt_device(m))
                mid_id = str(registry_id_of(m) or m.get("id") or "")
                kids = children_of.get(mid_id, [])
                for i, child in enumerate(kids):
                    prefix = "  └─" if i == len(kids) - 1 else "  ├─"
                    parts.append(self._fmt_device(child, indent=prefix + " "))
                if not kids:
                    parts.append("  └─ (하위 디바이스 없음)")

        # 직접 연결
        if direct:
            parts.append("─── 직접 연결 (direct_to_system) ───")
            for d in direct:
                parts.append(self._fmt_device(d))

        # 매핑 못된 디바이스
        if unmatched:
            parts.append("─── 부모 미확인 ───")
            for d in unmatched:
                parts.append(self._fmt_device(d) + f" (parent_id={d.get('parent_id')})")

        return "\n".join(parts) if parts else "(연결된 디바이스 없음)"

    def _parse(self, response: str) -> Optional[dict[str, Any]]:
        if not response:
            return None
        match = re.search(r'\{.*\}', response.strip(), re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None
