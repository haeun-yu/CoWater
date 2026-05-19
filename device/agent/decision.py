"""
Decision Engine: LLM-primary 의사결정 엔진

Critical rule(즉각 안전 조치)만 rule로 처리하고, 나머지 모든 운용 판단은 LLM이 수행합니다.

흐름:
1. Critical 확인 → 해당하면 LLM 무시하고 즉시 반환
2. 캐시된 마지막 LLM 결정 적용
3. 백그라운드로 다음 LLM 결정 요청 (non-blocking)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

from agent.state import AgentState, utc_now
from skills.catalog import SkillCatalog

try:
    from agent.llm_client import make_llm_client
except ImportError:
    make_llm_client = None

logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(self, agent_config: dict[str, Any], skills: SkillCatalog) -> None:
        self.agent_config = agent_config
        self.skills = skills
        self._cached_decision: Optional[dict[str, Any]] = None
        self._llm_pending: bool = False

        if not make_llm_client:
            raise RuntimeError("LLM client factory is unavailable")
        try:
            self.llm_client = make_llm_client(agent_config.get("llm", {}))
        except Exception as e:
            raise RuntimeError(f"LLM 클라이언트 초기화 실패: {e}") from e
        self.llm_enabled = True

    def decide(
        self,
        state: AgentState,
        telemetry: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        context: runtime이 tool 읽기값으로 채운 추가 정보
                 (obstacles, route, attitude, battery_detail, acoustic, tether 등)
        """
        context = context or {}
        actions = set(self.skills.list_actions())

        # 1. Critical safety check — LLM 없이 즉시 실행
        critical = self._check_critical(state, telemetry, context, actions)
        if critical:
            state.last_decision = critical
            return critical

        # 2. 캐시된 LLM 결정 적용
        decision = {
            "at": utc_now(),
            "mode": "llm" if self._cached_decision else "initializing",
            "llm_enabled": self.llm_enabled,
            "recommendations": (self._cached_decision or {}).get("recommendations", []),
            "llm_analysis": self._cached_decision,
        }

        # 3. 다음 LLM 결정 백그라운드 요청 (중복 방지)
        if self.llm_enabled and self.llm_client and not self._llm_pending:
            self._llm_pending = True
            asyncio.create_task(self._request_llm_decision(state, telemetry, context))

        state.last_decision = decision
        return decision

    # ──────────────────────────────────────────────
    # Critical rules
    # ──────────────────────────────────────────────

    def _check_critical(
        self,
        state: AgentState,
        telemetry: dict[str, Any],
        context: dict[str, Any],
        actions: set[str],
    ) -> Optional[dict[str, Any]]:
        cfg = self.agent_config.get("rules", {}).get("critical", {})
        battery = float(telemetry.get("battery_percent") or 100)
        device_type = str(state.device_type or "").upper()

        # 배터리 긴급 (모든 디바이스)
        if battery <= float(cfg.get("battery_emergency_percent", 10)):
            action = self._pick_action(
                device_type, actions,
                auv_rov_preferred=["emergency_ascent", "surface", "move_up"],
                surface_preferred=["emergency_stop", "abort_mission", "hold_position"],
            )
            return self._critical(action, {"reason": "battery_emergency", "battery_percent": battery})

        # 충돌 직전 (USV / CONTROL_SHIP)
        if device_type in ("USV", "CONTROL_SHIP"):
            nearest = float((context.get("obstacles") or {}).get("nearest_obstacle_distance", 999))
            if nearest <= float(cfg.get("obstacle_emergency_m", 5)):
                action = self._pick_action(device_type, actions, surface_preferred=["emergency_stop", "hold_position"])
                return self._critical(action, {"reason": "collision_imminent", "distance_m": nearest})

        # 수심 한계 초과 (AUV)
        if device_type == "AUV":
            depth = float(telemetry.get("depth") or 0)
            if depth >= float(cfg.get("max_depth_m", 80)):
                action = self._pick_action(device_type, actions, auv_rov_preferred=["emergency_ascent", "surface"])
                return self._critical(action, {"reason": "depth_limit", "depth_m": depth})

        # 수심 한계 초과 (ROV)
        if device_type == "ROV":
            depth = abs(float((telemetry.get("position") or {}).get("altitude", 0)))
            if depth >= float(cfg.get("max_depth_m", 200)):
                action = self._pick_action(device_type, actions, auv_rov_preferred=["move_up", "abort_mission"])
                return self._critical(action, {"reason": "depth_limit", "depth_m": depth})

            # 테더 장력 위험 (ROV)
            tether_status = (context.get("tether") or {}).get("status", "good")
            if tether_status == "critical":
                action = self._pick_action(device_type, actions, auv_rov_preferred=["move_up"])
                return self._critical(action, {"reason": "tether_tension_critical"})

        return None

    def _pick_action(
        self,
        device_type: str,
        actions: set[str],
        auv_rov_preferred: list[str] | None = None,
        surface_preferred: list[str] | None = None,
    ) -> str:
        preferred = (
            auv_rov_preferred if device_type in ("AUV", "ROV") and auv_rov_preferred
            else surface_preferred or []
        )
        for a in preferred:
            if a in actions:
                return a
        return next(iter(actions), "noop")

    def _critical(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "at": utc_now(),
            "mode": "critical_rule",
            "llm_enabled": self.llm_enabled,
            "recommendations": [{
                "action": action,
                "priority": "critical",
                "confidence": 1.0,
                "source": "critical_rule",
                "params": params,
            }],
            "llm_analysis": None,
        }

    # ──────────────────────────────────────────────
    # LLM decision pipeline
    # ──────────────────────────────────────────────

    async def _request_llm_decision(
        self,
        state: AgentState,
        telemetry: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        try:
            prompt = self._build_llm_prompt(state, telemetry, context)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)
            response = await self.llm_client.generate(prompt=prompt, timeout=timeout)
            parsed = self._parse_llm_response(response)
            if parsed:
                self._cached_decision = parsed
                actions = [r.get("action") for r in parsed.get("recommendations", [])]
                logger.debug(f"LLM 결정: {actions} | {parsed.get('reasoning', '')}")
        except Exception as e:
            logger.debug(f"LLM 결정 오류: {e}")
        finally:
            self._llm_pending = False

    def _parse_llm_response(self, response: str) -> Optional[dict[str, Any]]:
        if not response:
            return None
        match = re.search(r'\{.*\}', response.strip(), re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return None
        action = data.get("action")
        if not action:
            return None
        return {
            "recommendations": [{
                "action": action,
                "priority": data.get("priority", "normal"),
                "confidence": float(data.get("confidence", 0.7)),
                "source": "llm",
                "params": data.get("params", {}),
            }],
            "reasoning": data.get("reasoning", ""),
            "timestamp": utc_now(),
        }

    # ── action descriptions per device type ──────────
    _ACTION_DESC: dict[str, dict[str, str]] = {
        "USV": {
            "route_move":     "지정 웨이포인트로 이동 (params: target_lat, target_lon, speed_mps)",
            "hold_position":  "현재 위치 유지, 표류 방지",
            "return_to_base": "기지로 귀환 — 배터리 부족·임무 완료 시",
            "slow_down":      "속도 감소 (params: target_speed_mps) — 파고·장애물 대응",
            "follow_target":  "지정 대상 추적 (params: target_id)",
            "abort_mission":  "현재 임무 안전하게 중단, 대기",
            "emergency_stop": "즉각 정지 — 충돌 직전 전용, 복구 필요",
        },
        "AUV": {
            "dive_to_depth":    "목표 수심으로 잠수 (params: depth_m)",
            "hold_depth":       "현재 수심 유지",
            "surface":          "수면으로 상승 — 통신 회복·임무 완료",
            "follow_route":     "수중 항로 추종",
            "scan_area":        "소나 탐색 수행 (params: area)",
            "abort_mission":    "임무 중단, 수면 상승 준비",
            "emergency_ascent": "긴급 부상 — 배터리·통신 두절·수심 초과 시",
        },
        "ROV": {
            "move_forward":   "전진",
            "move_up":        "상승 — 수심 이탈·테더 위험 시",
            "rotate":         "회전 (params: angle_deg)",
            "grab_object":    "매니퓰레이터로 물체 파지",
            "release_object": "물체 해제",
            "adjust_lights":  "조명 조절 (params: brightness)",
            "record_video":   "영상 녹화 시작/중지",
        },
        "CONTROL_SHIP": {
            "route_move":          "함정 항로 이동",
            "hold_position":       "현재 위치 유지",
            "manage_tether_length":"ROV 테더 길이 조절 (params: length_m)",
            "coordinate_children": "하위 에이전트 조율",
            "manage_rov_power":    "ROV 전력 관리",
            "capture_video":       "ROV 영상 캡처",
            "relay_data":          "데이터 중계",
        },
    }

    def _build_llm_prompt(
        self,
        state: AgentState,
        telemetry: dict[str, Any],
        context: dict[str, Any],
    ) -> str:
        device_type = str(state.device_type or "UNKNOWN").upper()
        actions = list(self.skills.list_actions())
        position = telemetry.get("position") or {}
        motion = telemetry.get("motion") or {}
        battery = context.get("battery_detail") or {"percent": telemetry.get("battery_percent", 100)}
        tasks = list(state.tasks.values()) if state.tasks else []

        # 레이어별 역할 설명
        layer_role = {
            "lower":  "하위 실행 에이전트 — 시스템이 할당한 임무를 직접 수행합니다.",
            "middle": "중간 조율 에이전트 — 하위 디바이스를 관리하며 임무를 배분합니다.",
        }.get(state.layer, "에이전트")

        # 통신 경로 (state가 아는 실제 계층 정보)
        if state.route_mode == "via_parent" and state.parent_id:
            comm_line = f"통신 경로: 부모 에이전트(id={state.parent_id})를 경유 → 시스템"
        elif state.route_mode == "direct_to_system":
            comm_line = "통신 경로: 시스템 직접 연결"
        else:
            comm_line = f"통신 경로: {state.route_mode or '미확인'}"

        # action 설명 (현재 디바이스 타입에 맞는 것만)
        action_descs = self._ACTION_DESC.get(device_type, {})
        action_lines = "\n".join(
            f"  - {a}: {action_descs.get(a, '(설명 없음)')}"
            for a in actions
        )

        # 디바이스별 센서 섹션
        sensor_lines: list[str] = []
        bat_pct = float(battery.get("percent", 100))
        bat_min = battery.get("estimated_remaining_minutes", "?")

        if device_type in ("USV", "CONTROL_SHIP"):
            att = context.get("attitude") or {}
            obs = context.get("obstacles") or {}
            route = context.get("route") or {}
            nearest = float(obs.get("nearest_obstacle_distance", 999))
            roll = float(att.get("roll", 0))

            sensor_lines.append(f"자세: roll={roll:.1f}° pitch={att.get('pitch', 0):.1f}° "
                                 f"({'파고 주의 — 속도 줄일 것' if abs(roll) > 5 else '양호'})")
            sensor_lines.append(f"장애물: 최근접 {nearest:.0f}m "
                                 f"({'⚠ 회피 필요' if nearest < 30 else '안전'})")
            sensor_lines.append(f"항로: {route.get('progress_percent', 0):.0f}% 완료, "
                                 f"잔여 웨이포인트 {route.get('remaining_waypoints', 0)}개")
            if state.layer == "middle" and state.children:
                child_lines = []
                for cid, c in state.children.items():
                    cname = c.get("name", cid)
                    ctype = c.get("device_type", "?")
                    cbat  = c.get("last_battery_percent") or c.get("battery_percent")
                    cconn = c.get("connected", c.get("last_heartbeat_at") is not None)
                    cline = f"{cname}({ctype}) {'온라인' if cconn else '오프라인'}"
                    if cbat is not None:
                        cline += f" 배터리={float(cbat):.0f}%"
                    child_lines.append(cline)
                sensor_lines.append(
                    f"관리 하위 에이전트 {len(state.children)}대:\n" +
                    "\n".join(f"    · {l}" for l in child_lines)
                )

        elif device_type == "AUV":
            depth = float(telemetry.get("depth", 0))
            acoustic = context.get("acoustic") or {}
            route = context.get("route") or {}
            sig = float(acoustic.get("signal_strength", 0))
            sensor_lines.append(f"수심: {depth:.1f}m")
            sensor_lines.append(f"수중통신: 연결={acoustic.get('connected', False)}, "
                                 f"신호강도={sig:.2f} "
                                 f"({'⚠ 통신 불안정 — surface 고려' if sig < 0.3 else '양호'})")
            sensor_lines.append(f"임무 진행률: {route.get('progress_percent', 0):.0f}%")

        elif device_type == "ROV":
            depth = abs(float(position.get("altitude", 0)))
            tether = context.get("tether") or {}
            tension = float(tether.get("tension_newtons", 0))
            tether_status = tether.get("status", "good")
            sensor_lines.append(f"작업 수심: {depth:.1f}m")
            sensor_lines.append(f"테더: {tether.get('length_meters', 0):.0f}m 전개, "
                                 f"장력={tension:.0f}N "
                                 f"({'⚠ 장력 위험' if tether_status != 'good' else '정상'})")

        sensor_section = "\n".join(f"  {l}" for l in sensor_lines) or "  (센서 정보 없음)"

        # 판단 우선순위 (디바이스별)
        priority_guide = {
            "USV": (
                "1순위 안전: 장애물 30m 이내면 slow_down, 5m 이내면 emergency_stop\n"
                "2순위 항법: roll >5° 지속 시 slow_down으로 안정화\n"
                "3순위 배터리: 30% 이하는 경고, 10% 이하면 return_to_base\n"
                "4순위 임무: 배터리·안전 여유 있으면 route_move 또는 임무 지속"
            ),
            "AUV": (
                "1순위 안전: 통신 신호 <0.3이면 surface, 수심 한계 접근 시 hold_depth\n"
                "2순위 배터리: 30% 이하 경고, 10% 이하면 surface 후 귀환 판단\n"
                "3순위 임무: 통신·배터리 여유 있으면 scan_area 또는 follow_route"
            ),
            "ROV": (
                "1순위 안전: 테더 장력 위험 시 move_up, 수심 한계 시 move_up\n"
                "2순위 배터리: 30% 이하면 경고, 10% 이하면 move_up 후 abort_mission\n"
                "3순위 임무: 정상 상태면 현재 작업 지속"
            ),
            "CONTROL_SHIP": (
                "1순위 하위 에이전트 조율: 이상 감지 시 coordinate_children\n"
                "2순위 위치: 임무 지역 이탈 시 route_move\n"
                "3순위 통신: ROV 연결 이상 시 manage_rov_power"
            ),
        }.get(device_type, "안전을 최우선으로 판단하세요.")

        return f"""당신은 {device_type} 자율 에이전트입니다.
역할: {layer_role}
{comm_line}
현재 데이터를 바탕으로 즉각 수행할 action 하나를 결정하세요.

## 현재 상태
- 위치: lat={position.get('latitude', 0):.5f}, lon={position.get('longitude', 0):.5f}
- 속도: {motion.get('speed', 0):.2f} m/s, 방향: {motion.get('heading', 0):.1f}°
- 배터리: {bat_pct:.1f}% (잔여 약 {bat_min}분)

## 센서
{sensor_section}

## 현재 임무
{json.dumps(tasks, ensure_ascii=False) if tasks else "없음"}

## 판단 우선순위
{priority_guide}

## 수행 가능한 action
{action_lines}

위 판단 우선순위에 따라 action 하나를 결정하세요.
JSON 형식으로만 응답하세요. 설명 없이 JSON만:
{{
  "action": "<위 목록 중 하나>",
  "params": {{}},
  "priority": "normal" | "high",
  "confidence": 0.0~1.0,
  "reasoning": "<판단 근거 — 어떤 수치가 결정적이었나>"
}}"""
