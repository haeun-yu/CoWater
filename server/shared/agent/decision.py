"""
System Agent 의사결정 엔진 (LLM-primary)

- 모든 사용자 명령: LLM이 fleet 전체 컨텍스트를 보고 판단
- 이상 탐지: SYS_ANOMALY_DETECTED 이벤트로 처리
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
        "name": "get_insights",
        "description": "시스템 인사이트 및 성능 분석 데이터 조회",
        "parameters": {},
    },
    {
        "name": "plan_mission",
        "description": "새 미션 계획 생성. 사용자가 작전/임무 수행을 요청할 때 사용. 실행까지 원하면 이후 approve_mission을 호출하세요",
        "parameters": {"goal": {"type": "string", "description": "미션 목표 설명"}},
    },
    {
        "name": "approve_mission",
        "description": "plan_mission으로 생성된 미션을 승인하고 즉시 실행. plan_mission 결과의 approval_id가 필요",
        "parameters": {"approval_id": {"type": "string", "description": "plan_mission 결과에서 받은 approval_id"}},
    },
    {
        "name": "generate_report",
        "description": "현재 시스템 전체 상태 종합 리포트 생성. 장치·미션·경보·인사이트를 분석한 한국어 리포트를 자동 작성. 리포트/분석/요약 요청 시 사용",
        "parameters": {},
    },
    {
        "name": "final_answer",
        "description": "수집한 정보를 바탕으로 사용자에게 최종 답변 전달. 필요한 정보를 모두 준비한 뒤에만 호출",
        "parameters": {"response": "사용자에게 전달할 최종 답변 텍스트"},
    },
]


class DecisionEngine:
    def __init__(self, agent_config: dict[str, Any], skills: SkillCatalog, agent_profile: Any = None) -> None:
        self.agent_config = agent_config
        self.skills = skills
        self.agent_profile = agent_profile

        llm_config = agent_config.get("llm", {})

        # LLM is required, no fallback
        if not make_llm_client:
            raise RuntimeError("LLM client factory unavailable")

        self.llm_client = make_llm_client(llm_config)
        logger.info("LLM client initialized successfully")

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
        try:
            prompt = self._strategies_prompt(goal, mission_type, location, devices)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                error_dict = self._normalize_llm_error(error_ctx)
                logger.error(f"LLM proposal strategies 생성 실패: {error_dict.get('message', '')}")
                return None, error_dict

            result = self._parse(response) if response else None
            if result:
                strategies = result.get("strategies") or []
                if len(strategies) >= 3:
                    logger.info(f"LLM proposal strategies 생성 성공: {len(strategies)} strategies")
                    return strategies[:3], None
                else:
                    logger.error(f"LLM returned {len(strategies)} strategies (need 3)")
                    return None, {"error_type": "incomplete_response", "message": "LLM returned insufficient strategies"}
            else:
                logger.error("LLM proposal strategies 응답 파싱 실패")
                return None, {"error_type": "parse_error", "message": "Failed to parse LLM response"}

        except Exception as e:
            logger.error(f"LLM proposal strategies 생성 중 오류: {type(e).__name__}: {e}")
            return None, {
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

    # ── action semantics ──────────────────────────
    _ACTION_DESC = {
        "mission.plan":    "임무 계획 수립 (params: mission_type, location)",
        "mission.assign":  "디바이스에 전체 임무 배정 (mine_detection 등 복합 임무)",
        "task.assign":     "단일 작업 배정 (params: action, location, target_device_id)",
        "approve_response":"시스템 대응 승인 및 실행 지시",
        "route_direct":    "디바이스에 직접 명령 전달 (중간 계층 없이)",
        "route_via_middle":"중간 계층 에이전트를 통해 명령 전달",
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
    # Role instructions helper
    # ──────────────────────────────────────────────

    def _get_role_instructions(self, context: dict[str, Any] | None = None) -> str:
        """Get role-specific instructions from agent_profile. Falls back to default if not available."""
        if self.agent_profile and hasattr(self.agent_profile, "render_instructions"):
            return self.agent_profile.render_instructions(context or {})
        return "당신은 CoWater 해양 통합 운용 플랫폼의 AI 지휘관입니다."

    # ──────────────────────────────────────────────
    # Prompt builders
    # ──────────────────────────────────────────────

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

        role_instructions = self._get_role_instructions()
        return f"""{role_instructions}

## 운용자 명령
{json.dumps(command, ensure_ascii=False)}

명령 해석 지침:
- action 필드가 명확하면 그대로 사용
- 자연어 reason/params에 대상 디바이스 이름이 있으면 fleet에서 찾아 id 매핑
- 대상이 불명확하면 임무 수행 가능한 디바이스 중 배터리가 가장 높은 것 선택
- 명령이 현재 fleet 상태상 불가능하면 action을 "escalate"로 설정하고 reasoning에 이유 기술

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
        role_instructions = self._get_role_instructions()
        return f"""{role_instructions}

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
        # 마크다운 코드 펜스(```json ... ```) 제거
        text = re.sub(r'```[a-zA-Z]*\n?', '', response).strip()

        # 첫 번째 '{' 위치에서 시작해 중첩 괄호를 추적해 올바른 JSON 블록 추출
        start = text.find('{')
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        # JSON 문자열 내 리터럴 줄바꿈을 \n으로 교체 후 재시도
                        sanitized = self._sanitize_json_string(candidate)
                        try:
                            return json.loads(sanitized)
                        except json.JSONDecodeError:
                            return None
        return None

    @staticmethod
    def _sanitize_json_string(text: str) -> str:
        """JSON 문자열 값 내부의 리터럴 줄바꿈/탭을 이스케이프 시퀀스로 교체"""
        result = []
        in_string = False
        escape = False
        for ch in text:
            if escape:
                result.append(ch)
                escape = False
                continue
            if ch == '\\' and in_string:
                result.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string and ch == '\n':
                result.append('\\n')
                continue
            if in_string and ch == '\r':
                result.append('\\r')
                continue
            if in_string and ch == '\t':
                result.append('\\t')
                continue
            result.append(ch)
        return ''.join(result)

    # ──────────────────────────────────────────────
    # ReAct 에이전트 루프 (N-step tool calling)
    # ──────────────────────────────────────────────

    @staticmethod
    def _summarize_history(history: list) -> str:
        lines = []
        for step in history:
            action = step["action"]
            result = step["result"]
            if action == "get_devices" and isinstance(result, list):
                summary = f'장치 {len(result)}개: ' + ", ".join(
                    f'{d.get("name","??")}({d.get("status","??")}, 배터리:{d.get("battery","?")}%)'
                    for d in result
                )
            elif action == "get_missions" and isinstance(result, list):
                summary = f'미션 {len(result)}건: ' + ", ".join(
                    f'{m.get("title","??")}/{m.get("status","??")}' for m in result[:5]
                )
            elif action == "get_insights" and isinstance(result, list):
                summary = f'인사이트 {len(result)}건'
            elif isinstance(result, dict) and "message" in result:
                summary = result["message"]
            else:
                summary = json.dumps(result, ensure_ascii=False, default=str)[:300]
            lines.append(f'[{action}] {summary}')
        return "\n".join(lines)

    def _react_prompt(self, user_input: str, tools: list, history: list, *, force_final: bool = False) -> str:
        history_text = self._summarize_history(history) if history else ""

        # force_final: 수집된 데이터로 무조건 답변
        if force_final:
            return (
                f'CoWater 해양 운용 AI. JSON만 출력.\n'
                f'운용자 질문: "{user_input}"\n'
                f'수집 결과:\n{history_text}\n\n'
                f'위 데이터로 한국어 답변. JSON만:\n'
                f'{{"thought":"근거","action":"final_answer","action_input":{{"response":"한국어답변"}}}}'
            )

        last_action = history[-1]["action"] if history else None

        # 히스토리가 있으면 → 다음 행동 결정
        if history:
            # plan_mission 이후: 사용자가 실행 원하면 approve_mission, 아니면 final_answer
            if last_action == "plan_mission":
                last_result = history[-1].get("result", {})
                approval_id = last_result.get("approval_id", "")
                if approval_id:
                    next_hint = (
                        f'사용자가 실행을 원하면 approve_mission을 호출하세요.\n'
                        f'계획만 원하면 final_answer를 호출하세요.\n'
                        f'approve_mission 예시: {{"thought":"실행","action":"approve_mission","action_input":{{"approval_id":"{approval_id}"}}}}'
                    )
                else:
                    next_hint = f'final_answer로 계획 내용을 한국어로 전달하세요.'
            else:
                next_hint = f'final_answer로 한국어 답변을 전달하세요.'

            return (
                f'CoWater 해양 운용 AI. JSON만 출력.\n'
                f'운용자 질문: "{user_input}"\n'
                f'수집 결과:\n{history_text}\n\n'
                f'→ {next_hint}\n'
                f'출력: {{"thought":"이유","action":"선택한도구","action_input":{{}}}}'
            )

        # 첫 단계: 필요한 도구 선택
        valid_names = [t["name"] for t in tools]
        tool_lines = []
        for t in tools:
            name = t["name"]
            desc = t["description"].split(".")[0]
            params = t.get("parameters") or {}
            sig = ", ".join(f'{k}="..."' for k in params) if params else ""
            tool_lines.append(f'  "{name}"({sig}): {desc}' if sig else f'  "{name}": {desc}')

        return (
            f'CoWater 해양 운용 AI. JSON만 출력.\n'
            f'명령: "{user_input}"\n\n'
            f'허용 도구 (action은 반드시 아래 중 하나):\n'
            + "\n".join(tool_lines) + "\n\n"
            f'허용 action 목록: {json.dumps(valid_names, ensure_ascii=False)}\n\n'
            f'출력 (action에 위 목록 중 하나만 사용):\n'
            f'{{"thought":"선택 이유","action":"허용된도구명","action_input":{{}}}}'
        )

    async def react_step(
        self,
        user_input: str,
        tools: list,
        history: list,
        timeout: Optional[int] = None,
        *,
        force_final: bool = False,
    ) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        """ReAct 루프 단일 스텝: LLM이 다음 행동(도구 호출 또는 최종 답변)을 결정"""
        try:
            prompt = self._react_prompt(user_input, tools, history, force_final=force_final)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)
            if error_ctx is not None:
                return None, self._normalize_llm_error(error_ctx)
            result = self._parse(response) if response else None
            if not result:
                logger.warning(f"ReAct step 파싱 실패 (raw 300자): {(response or '')[:300]}")
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
        state: AgentState,
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        """LLM으로 fleet 전체 복합 패턴 이상 탐지

        Returns: (analysis_result, error_context)
        """
        try:
            prompt = self._fleet_pattern_prompt(devices, missions)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                error_dict = self._normalize_llm_error(error_ctx)
                logger.error(f"LLM fleet pattern 분석 실패: {error_dict.get('message', '')}")
                return {}, error_dict

            result = self._parse(response) if response else None
            if result:
                logger.info(f"LLM fleet pattern 분석 성공: {result.get('severity', 'normal')}")
                return result, None
            else:
                logger.error("LLM fleet pattern 응답 파싱 실패")
                return {}, {"error_type": "parse_error", "message": "Failed to parse LLM response"}

        except Exception as e:
            logger.error(f"LLM fleet pattern 분석 중 오류: {type(e).__name__}: {e}")
            return {}, {
                "error_type": "unknown_error",
                "message": str(e),
            }

    def _rule_based_fleet_check(
        self,
        devices: list[dict[str, Any]],
        missions: list[dict[str, Any]],
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
    ) -> str:
        """Fleet 복합 패턴 분석 프롬프트"""
        missions_summary = "\n".join(
            f"  - {m.get('title', 'Unknown')} (상태: {m.get('status', 'UNKNOWN')}, id: {m.get('mission_id')})"
            for m in missions[:10]
        ) or "  (진행 중인 임무 없음)"

        return f"""당신은 CoWater 해양 통합 운용 플랫폼의 시스템 감시 AI입니다.
Fleet 전체의 복합 패턴 이상을 분석합니다.

## 현재 Fleet 상태
{self._fleet_summary(devices)}

## 진행 중인 임무
{missions_summary}

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
        try:
            prompt = self._insight_summary_prompt(goal, mission_type, devices, context)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                logger.error(f"LLM insight 요약 생성 실패: {error_ctx}")
                return {}, self._normalize_llm_error(error_ctx)

            result = self._parse(response) if response else None
            if result and result.get("summary"):
                logger.info("LLM insight 요약 생성 성공")
                return result, None
            else:
                logger.error("LLM insight 요약 응답 파싱 실패")
                return {}, {"error_type": "parse_error", "message": "Failed to parse LLM response"}

        except Exception as e:
            logger.error(f"LLM insight 요약 생성 중 오류: {type(e).__name__}: {e}")
            return {}, {"error_type": "unknown_error", "message": str(e)}

    async def generate_fleet_report(
        self,
        devices: list[dict[str, Any]],
        missions: list[dict[str, Any]],
        insights: list[dict[str, Any]],
        state: AgentState,
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        """LLM으로 fleet 전체 현황 한국어 리포트 생성"""
        try:
            prompt = self._fleet_report_prompt(devices, missions, insights)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response, error_ctx = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            if error_ctx is not None:
                logger.error(f"LLM fleet 리포트 생성 실패: {error_ctx}")
                return {}, self._normalize_llm_error(error_ctx)

            result = self._parse(response) if response else None
            if result and result.get("report"):
                logger.info("LLM fleet 리포트 생성 성공")
                return result, None
            else:
                logger.error("LLM fleet 리포트 응답 파싱 실패")
                return {}, {"error_type": "parse_error", "message": "Failed to parse LLM response"}

        except Exception as e:
            logger.error(f"LLM fleet 리포트 생성 중 오류: {type(e).__name__}: {e}")
            return {}, {"error_type": "unknown_error", "message": str(e)}

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
