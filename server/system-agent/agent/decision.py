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

# RequestHandler가 LLM에게 노출하는 도구 목록
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_devices",
        "description": "연결된 장치 목록 조회 (이름, 타입, 온라인 여부, 배터리, 위치, 가능한 액션)",
        "parameters": {},
    },
    {
        "name": "get_missions",
        "description": "등록된 미션 목록 조회 (제목, 상태, 우선순위, 생성 시각)",
        "parameters": {},
    },
    {
        "name": "get_alerts",
        "description": "발생한 경보 목록 조회 (심각도, 유형, 상태, 발생 시각)",
        "parameters": {},
    },
    {
        "name": "get_insights",
        "description": "시스템 인사이트 및 성능 분석 데이터 조회",
        "parameters": {},
    },
    {
        "name": "plan_mission",
        "description": "새 미션 계획 생성. 사용자가 작전/임무 수행을 요청할 때 사용",
        "parameters": {"goal": "미션 목표 설명"},
    },
    {
        "name": "final_answer",
        "description": "수집한 정보를 바탕으로 사용자에게 최종 답변 전달. 필요한 정보를 모두 준비한 뒤에만 호출",
        "parameters": {"response": "사용자에게 전달할 최종 답변 텍스트"},
    },
]


class DecisionEngine:
    def __init__(self, agent_config: dict[str, Any], skills: SkillCatalog) -> None:
        self.agent_config = agent_config
        self.skills = skills

        llm_config = agent_config.get("llm", {})
        llm_enabled_in_config = llm_config.get("enabled", True)

        # LLM disabled in config
        if not llm_enabled_in_config:
            logger.info("LLM disabled in config, using rule-based decision making")
            self.llm_client = None
            self.llm_enabled = False
            return

        # LLM import unavailable
        if not make_llm_client:
            logger.warning("LLM client factory unavailable, falling back to rule-based mode")
            self.llm_client = None
            self.llm_enabled = False
            return

        # Try to initialize LLM
        try:
            self.llm_client = make_llm_client(llm_config)
            logger.info("LLM client initialized successfully")
            self.llm_enabled = True
        except Exception as e:
            logger.warning(f"LLM initialization failed: {e}, falling back to rule-based mode")
            self.llm_client = None
            self.llm_enabled = False

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

    async def analyze_intent(
        self,
        goal: str,
        devices: list[dict[str, Any]],
        state: AgentState,
    ) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        """
        사용자 자연어 목표 → mission_type, location, priority 분류

        Returns: (llm_result, error_context)
        - If successful: (intent_dict with mission_type/location/priority, None)
        - If failed: (None, error_dict)
        """
        if not self.llm_enabled or not self.llm_client:
            logger.debug("LLM disabled, cannot analyze intent")
            return None, {"error_type": "llm_disabled", "message": "LLM disabled in config"}

        try:
            prompt = self._intent_prompt(goal, devices, state)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                error_dict = self._normalize_llm_error(error_ctx)
                error_type = str(error_dict.get("error_type") or "unknown_error")
                log_fn = logger.warning if error_type == "circuit_open" else logger.error
                log_fn(
                    f"LLM intent 분석 실패 [{error_type}] "
                    f"(시도 {error_dict.get('attempt_number', 1)}/{error_dict.get('max_attempts', 3)}, "
                    f"{error_dict.get('elapsed_ms', 0)}ms): {error_dict.get('message', '')}"
                )
                return None, error_dict

            result = self._parse(response) if response else None
            if result:
                logger.info(f"LLM intent 분석 성공: {result.get('mission_type', 'unknown')} - {result.get('reasoning', '')[:80]}")
            else:
                logger.warning(f"LLM intent 분석 응답 파싱 실패 (응답: {response[:100] if response else 'empty'})")

            return result, None

        except Exception as e:
            logger.error(f"LLM intent 분석 중 예기치 않은 오류: {type(e).__name__}: {e}")
            error_dict = {
                "error_type": "unknown_error",
                "message": str(e),
                "recovery_strategy": "fallback",
            }
            return None, error_dict

    async def generate_proposal_strategies(
        self,
        goal: str,
        mission_type: str,
        location: dict[str, Any],
        devices: list[dict[str, Any]],
        state: AgentState,
    ) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
        """
        LLM에게 3가지 mission strategy 변형 생성 요청

        Returns: (strategies_list, error_context)
        Each strategy: {"title": str, "approach": str, "summary": str, "priority": str}
        """
        if not self.llm_enabled or not self.llm_client:
            logger.debug("LLM disabled, returning rule-based strategies")
            return self._rule_based_strategies(mission_type), {"error_type": "llm_disabled"}

        try:
            prompt = self._strategies_prompt(goal, mission_type, location, devices)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                error_dict = self._normalize_llm_error(error_ctx)
                logger.warning(f"LLM proposal strategies 생성 실패, rule-based fallback 사용: {error_dict.get('message', '')}")
                return self._rule_based_strategies(mission_type), error_dict

            result = self._parse(response) if response else None
            if result:
                strategies = result.get("strategies") or []
                if len(strategies) >= 3:
                    logger.info(f"LLM proposal strategies 생성 성공: {len(strategies)} strategies")
                    return strategies[:3], None
                else:
                    logger.warning(f"LLM returned {len(strategies)} strategies (need 3), using rule-based fallback")
                    return self._rule_based_strategies(mission_type), {"error_type": "incomplete_response"}
            else:
                logger.warning("LLM proposal strategies 응답 파싱 실패, rule-based fallback 사용")
                return self._rule_based_strategies(mission_type), {"error_type": "parse_error"}

        except Exception as e:
            logger.error(f"LLM proposal strategies 생성 중 오류: {type(e).__name__}: {e}")
            return self._rule_based_strategies(mission_type), {
                "error_type": "unknown_error",
                "message": str(e),
            }

    def _rule_based_strategies(self, mission_type: str) -> list[dict[str, Any]]:
        """LLM 실패 시 mission_type에 맞는 3가지 기본 전략 반환"""
        base = mission_type.replace("_", " ").title()
        return [
            {
                "title": f"{base} 표준 작전",
                "approach": "standard",
                "summary": "균형 잡힌 표준 접근 방식으로 안정적인 작전 실행",
                "priority": "normal",
            },
            {
                "title": f"{base} 신속 작전",
                "approach": "fast",
                "summary": "최소 자원으로 신속 대응하는 효율적 접근",
                "priority": "high",
            },
            {
                "title": f"{base} 정밀 작전",
                "approach": "precise",
                "summary": "철저한 다단계 탐사로 정밀하게 실행하는 방식",
                "priority": "normal",
            },
        ]

    def _strategies_prompt(
        self,
        goal: str,
        mission_type: str,
        location: dict[str, Any],
        devices: list[dict[str, Any]],
    ) -> str:
        """3가지 전략 생성 LLM 프롬프트"""
        location_str = json.dumps(location or {}, ensure_ascii=False)
        devices_summary = self._fleet_summary(devices)

        return f"""당신은 CoWater 해양 통합 운용 플랫폼의 작전 계획 AI입니다.
주어진 미션에 대해 3가지 서로 다른 전략적 접근법을 제안합니다.

## 미션 정보
- 목표: {goal}
- 미션 타입: {mission_type}
- 작전 지역: {location_str}

## 현재 Fleet 상태
{devices_summary}

## 전략 개발 지침
3가지 전략은 각각 다른 우선순위를 반영해야 합니다:

1. **표준 작전** (approach: "standard")
   - 균형 잡힌 접근
   - 중간 정도의 투입 자원으로 안정적 실행
   - 작전 완료 시간: 중간

2. **신속 작전** (approach: "fast")
   - 빠른 대응 우선
   - 최소한의 필수 자원만 투입
   - 작전 완료 시간: 단축
   - 우선순위(priority): "high"

3. **정밀 작전** (approach: "precise")
   - 철저한 탐사 우선
   - 다단계 검증 포함
   - 확보 정확성: 최대
   - 작전 완료 시간: 장기

## 응답 형식
다음 JSON으로만 응답하세요. 설명 없이 JSON만:
{{
  "strategies": [
    {{
      "title": "<작전명 (한국어)>",
      "approach": "standard" | "fast" | "precise",
      "summary": "<전략 설명 (1-2문장, 한국어)>",
      "priority": "normal" | "high" | "low"
    }},
    ...
  ]
}}"""

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

    def _intent_prompt(
        self,
        goal: str,
        devices: list[dict[str, Any]],
        state: AgentState,
    ) -> str:
        return f"""당신은 CoWater 해양 통합 운용 플랫폼의 AI 지휘관입니다.
운용자의 자연어 요청을 분석하여 intent 타입을 분류합니다.

## 운용자 요청
"{goal}"

## Intent 타입 정의
- QUERY: 현재 상태 조회 (장치 상태, 배터리, 위치, 미션 목록 등)
- REPORT: 분석 리포트 요청 (요약, 분석, 인사이트, 보고서 등)
- MISSION: 작전/미션 실행 요청 (탐지, 조사, 점검, 모니터링, 출동 등)
- SYSTEM_CONTROL: 시스템 제어 (재시작, 정지, 긴급 명령 등)

## 현재 Fleet 상태
{self._fleet_summary(devices)}

## 응답 지침
- intent_type: 위 4가지 중 하나
- mission_type: MISSION일 때만 — mine_clearance | survey | inspection | monitoring | generic_mission (그 외 null)
- location: 언급된 위치 또는 null
- priority: CRITICAL | HIGH | NORMAL
- reasoning: 분류 근거

JSON 형식으로만 응답하세요. 설명 없이 JSON만:
{{
  "intent_type": "QUERY" | "REPORT" | "MISSION" | "SYSTEM_CONTROL",
  "mission_type": "<미션타입 또는 null>",
  "location": {{"area": "<지역명>" or null}},
  "priority": "CRITICAL" | "HIGH" | "NORMAL",
  "reasoning": "<분류 근거>"
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

    # ──────────────────────────────────────────────
    # ReAct 에이전트 루프 (N-step tool calling)
    # ──────────────────────────────────────────────

    def _react_prompt(self, user_input: str, tools: list, history: list) -> str:
        tool_lines = []
        for t in tools:
            params = ""
            if t.get("parameters"):
                params = " | 파라미터: " + ", ".join(
                    f"{k}: {v}" for k, v in t["parameters"].items()
                )
            tool_lines.append(f"  - {t['name']}: {t['description']}{params}")

        history_text = ""
        if history:
            history_text = "\n\n## 이전 단계 결과"
            for i, step in enumerate(history, 1):
                inp = step.get("input")
                inp_str = f" | 입력: {json.dumps(inp, ensure_ascii=False)}" if inp else ""
                result_str = json.dumps(step["result"], ensure_ascii=False, default=str)
                history_text += f"\n\n[{i}단계] 도구: {step['action']}{inp_str}\n결과: {result_str}"

        return (
            "당신은 CoWater 해양 통합 운용 플랫폼의 AI 어시스턴트입니다.\n"
            "사용자 명령을 처리하기 위해 필요한 도구를 순서대로 호출하세요.\n\n"
            f"## 사용자 명령\n\"{user_input}\"\n\n"
            "## 사용 가능한 도구\n" + "\n".join(tool_lines)
            + history_text
            + "\n\n## 지침\n"
            "- 명령 처리에 필요한 도구만 선택적으로 호출하세요. 불필요한 도구는 호출하지 마세요.\n"
            "- 충분한 정보가 모이면 즉시 final_answer를 호출해 사용자에게 답변하세요.\n"
            "- 반드시 JSON 형식으로만 응답하세요 (설명 없이 JSON만):\n\n"
            '{"thought": "<이 단계에서 무엇을 왜 할지>", "action": "<도구명>", "action_input": {...}}'
        )

    async def react_step(
        self,
        user_input: str,
        tools: list,
        history: list,
        timeout: Optional[int] = None,
    ) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        """ReAct 루프 단일 스텝: LLM이 다음 행동(도구 호출 또는 최종 답변)을 결정"""
        if not self.llm_enabled or not self.llm_client:
            return None, {"error_type": "llm_disabled", "message": "LLM disabled in config"}
        try:
            prompt = self._react_prompt(user_input, tools, history)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)
            if error_ctx is not None:
                return None, self._normalize_llm_error(error_ctx)
            result = self._parse(response) if response else None
            if not result:
                logger.warning(f"ReAct step 파싱 실패: {(response or '')[:120]}")
            return result, None
        except Exception as e:
            logger.error(f"ReAct step 오류: {type(e).__name__}: {e}")
            return None, {"error_type": "unknown_error", "message": str(e)}

    # ──────────────────────────────────────────────
    # Phase 3: SystemSentinel - 복합 패턴 분석
    # ──────────────────────────────────────────────

    async def analyze_fleet_patterns(
        self,
        devices: list[dict[str, Any]],
        missions: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
        state: AgentState,
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        """LLM으로 fleet 전체 복합 패턴 이상 탐지

        Returns: (analysis_result, error_context)
        """
        if not self.llm_enabled or not self.llm_client:
            return self._rule_based_fleet_check(devices, missions, alerts), {"error_type": "llm_disabled"}

        try:
            prompt = self._fleet_pattern_prompt(devices, missions, alerts)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                error_dict = self._normalize_llm_error(error_ctx)
                logger.warning(f"LLM fleet pattern 분석 실패, rule-based fallback: {error_dict.get('message', '')}")
                return self._rule_based_fleet_check(devices, missions, alerts), error_dict

            result = self._parse(response) if response else None
            if result:
                logger.info(f"LLM fleet pattern 분석 성공: {result.get('severity', 'normal')}")
                return result, None
            else:
                logger.warning("LLM fleet pattern 응답 파싱 실패, rule-based fallback")
                return self._rule_based_fleet_check(devices, missions, alerts), {"error_type": "parse_error"}

        except Exception as e:
            logger.error(f"LLM fleet pattern 분석 중 오류: {type(e).__name__}: {e}")
            return self._rule_based_fleet_check(devices, missions, alerts), {
                "error_type": "unknown_error",
                "message": str(e),
            }

    def _rule_based_fleet_check(
        self,
        devices: list[dict[str, Any]],
        missions: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """규칙 기반 fleet 이상 감지"""
        anomalies = []
        severity = "normal"

        low_battery_devices = [d for d in devices if d.get("last_battery_percent", 100) < 20]
        if low_battery_devices:
            anomalies.append({
                "type": "LOW_BATTERY",
                "devices": [d.get("name") for d in low_battery_devices],
                "message": f"{len(low_battery_devices)}개 디바이스 배터리 부족 (20% 이하)"
            })
            severity = "warning"

        offline_devices = [d for d in devices if not d.get("connected")]
        if offline_devices:
            anomalies.append({
                "type": "OFFLINE",
                "devices": [d.get("name") for d in offline_devices],
                "message": f"{len(offline_devices)}개 디바이스 오프라인"
            })
            severity = "warning"

        active_missions = [m for m in missions if m.get("status") in ["ACTIVE", "IN_PROGRESS"]]
        if len(active_missions) > len(devices):
            anomalies.append({
                "type": "RESOURCE_SHORTAGE",
                "missions": len(active_missions),
                "devices": len(devices),
                "message": f"활성 임무({len(active_missions)}) > 가용 디바이스({len(devices)})"
            })
            severity = "critical"

        return {
            "anomalies": anomalies,
            "severity": severity,
            "summary": f"규칙 기반 이상 탐지: {severity}",
            "recommended_actions": ["인적 검토 필요"] if severity != "normal" else []
        }

    def _fleet_pattern_prompt(
        self,
        devices: list[dict[str, Any]],
        missions: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
    ) -> str:
        """Fleet 복합 패턴 분석 프롬프트"""
        missions_summary = "\n".join(
            f"  - {m.get('title', 'Unknown')} (상태: {m.get('status', 'UNKNOWN')}, id: {m.get('mission_id')})"
            for m in missions[:10]
        ) or "  (진행 중인 임무 없음)"

        alerts_summary = "\n".join(
            f"  - {a.get('alert_type', 'Unknown')}: {a.get('message', 'No message')} (심각도: {a.get('severity', 'INFO')})"
            for a in alerts[-10:]
        ) or "  (최근 alerts 없음)"

        return f"""당신은 CoWater 해양 통합 운용 플랫폼의 시스템 감시 AI입니다.
Fleet 전체의 복합 패턴 이상을 분석합니다.

## 현재 Fleet 상태
{self._fleet_summary(devices)}

## 진행 중인 임무
{missions_summary}

## 최근 Alerts (최신 10개)
{alerts_summary}

## 분석 요청
다음 항목들의 **복합 패턴**을 분석하세요:
1. 배터리 급감 + 신호 약화 → 고장 의심
2. 다수 디바이스 동시 배터리 저하 → 기지 전원 문제
3. 활성 임무 수 > 가용 디바이스 → 자원 부족 경보
4. 진행 중인 임무 대비 실제 가용 자원 부족 → 임무 실패 가능성

## 응답 형식 (JSON만)
{{
  "anomalies": [
    {{"type": "PATTERN_TYPE", "message": "설명", "severity": "low|medium|high"}}
  ],
  "severity": "normal|warning|critical",
  "summary": "종합 분석 요약",
  "recommended_actions": ["조치1", "조치2"]
}}"""

    # ──────────────────────────────────────────────
    # Phase 4: InsightReporter - 한국어 요약
    # ──────────────────────────────────────────────

    async def generate_insight_summary(
        self,
        goal: str,
        mission_type: str,
        devices: list[dict[str, Any]],
        context: dict[str, Any],
        state: AgentState,
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        """LLM으로 insight summary + reason_summary 한국어 생성"""
        if not self.llm_enabled or not self.llm_client:
            return self._rule_based_insight_summary(mission_type), {"error_type": "llm_disabled"}

        try:
            prompt = self._insight_summary_prompt(goal, mission_type, devices, context)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                return self._rule_based_insight_summary(mission_type), self._normalize_llm_error(error_ctx)

            result = self._parse(response) if response else None
            if result and result.get("summary"):
                logger.info("LLM insight 요약 생성 성공")
                return result, None
            else:
                return self._rule_based_insight_summary(mission_type), {"error_type": "parse_error"}

        except Exception as e:
            logger.error(f"LLM insight 요약 생성 중 오류: {type(e).__name__}: {e}")
            return self._rule_based_insight_summary(mission_type), {"error_type": "unknown_error"}

    async def generate_fleet_report(
        self,
        devices: list[dict[str, Any]],
        missions: list[dict[str, Any]],
        insights: list[dict[str, Any]],
        state: AgentState,
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        """LLM으로 fleet 전체 현황 한국어 리포트 생성"""
        if not self.llm_enabled or not self.llm_client:
            return self._rule_based_fleet_report(devices, missions), {"error_type": "llm_disabled"}

        try:
            prompt = self._fleet_report_prompt(devices, missions, insights)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                return self._rule_based_fleet_report(devices, missions), self._normalize_llm_error(error_ctx)

            result = self._parse(response) if response else None
            if result and result.get("report"):
                logger.info("LLM fleet 리포트 생성 성공")
                return result, None
            else:
                return self._rule_based_fleet_report(devices, missions), {"error_type": "parse_error"}

        except Exception as e:
            logger.error(f"LLM fleet 리포트 생성 중 오류: {type(e).__name__}: {e}")
            return self._rule_based_fleet_report(devices, missions), {"error_type": "unknown_error"}

    def _rule_based_insight_summary(self, mission_type: str) -> dict[str, Any]:
        """규칙 기반 insight 요약"""
        base = mission_type.replace("_", " ").title()
        return {
            "summary": f"'{base}' 미션 제안이 준비되었습니다.",
            "reason_summary": "현재 디바이스 가용성 및 라우팅 상태를 고려하여 실행 가능합니다."
        }

    def _rule_based_fleet_report(
        self,
        devices: list[dict[str, Any]],
        missions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """규칙 기반 fleet 리포트"""
        online_count = sum(1 for d in devices if d.get("connected"))
        active_missions = [m for m in missions if m.get("status") in ["ACTIVE", "IN_PROGRESS"]]

        return {
            "report": f"Fleet 현황: 온라인 {online_count}/{len(devices)} 디바이스, 활성 임무 {len(active_missions)}개",
            "highlights": [
                f"운영 중인 디바이스: {online_count}개",
                f"진행 중인 임무: {len(active_missions)}개"
            ],
            "recommendations": []
        }

    def _insight_summary_prompt(
        self,
        goal: str,
        mission_type: str,
        devices: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> str:
        """Insight 요약 한국어 프롬프트"""
        location_str = json.dumps(context.get("location", {}), ensure_ascii=False) if context.get("location") else "미지정"

        return f"""당신은 CoWater 해양 통합 운용 플랫폼의 자연어 리포팅 AI입니다.
미션 제안에 대한 한국어 요약을 생성합니다.

## 미션 정보
- 목표: {goal}
- 미션 타입: {mission_type}
- 작전 지역: {location_str}

## 현재 Fleet 상태
{self._fleet_summary(devices)}

## 요청
다음 두 항목을 한국어로 생성하세요:

1. **summary**: 미션 제안의 한 문장 요약 (30-50자)
2. **reason_summary**: 왜 이 미션이 실행 가능한지 설명 (50-100자)

응답은 JSON만:
{{
  "summary": "한국어 제목",
  "reason_summary": "한국어 근거"
}}"""

    def _fleet_report_prompt(
        self,
        devices: list[dict[str, Any]],
        missions: list[dict[str, Any]],
        insights: list[dict[str, Any]],
    ) -> str:
        """Fleet 리포트 한국어 프롬프트"""
        online = sum(1 for d in devices if d.get("connected"))
        active_missions = [m for m in missions if m.get("status") in ["ACTIVE", "IN_PROGRESS"]]

        return f"""당신은 CoWater 해양 통합 운용 플랫폼의 자연어 리포팅 AI입니다.
Fleet 전체 현황에 대한 한국어 리포트를 생성합니다.

## Fleet 상태
- 온라인 디바이스: {online}/{len(devices)}개
- 진행 중인 임무: {len(active_missions)}개
- 최근 인사이트: {len(insights)}개

## 디바이스 상세
{self._fleet_summary(devices)}

## 요청
다음 항목들을 한국어로 생성하세요:

1. **report**: Fleet 전체 현황 리포트 (100-150자)
2. **highlights**: 주요 사항 3-5개 (리스트)
3. **recommendations**: 권고 조치 (필요 시)

응답은 JSON만:
{{
  "report": "한국어 리포트",
  "highlights": ["항목1", "항목2"],
  "recommendations": []
}}"""
