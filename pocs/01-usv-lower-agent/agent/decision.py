"""
Decision Engine: Agent의 의사결정 엔진

Rule 기반 decision(동기)과 LLM 분석(비동기)을 결합하여 최적의 행동을 권장합니다.
- Rule 기반: 빠르고 신뢰할 수 있는 즉각적인 결정
- LLM 분석: 복잡한 상황에서 추가 인사이트 제공 (논블로킹)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from agent.state import AgentState, utc_now
from skills.catalog import SkillCatalog

try:
    from shared.llm_client import make_llm_client
except ImportError:
    make_llm_client = None

logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    의사결정 엔진: Rule 기반 + LLM 분석

    하이브리드 접근:
    1. Rule 기반 decision (동기, 빠름): 배터리 경고, 속도 제한, 자식 조율
    2. LLM 분석 (비동기, 논블로킹): Ollama로 상황 분석 및 추가 권장사항

    LLM 호출이 decision loop를 블로킹하지 않도록 asyncio.create_task()를 사용합니다.
    """

    def __init__(self, agent_config: dict[str, Any], skills: SkillCatalog) -> None:
        """
        의사결정 엔진 초기화

        Args:
            agent_config: Agent 설정 (rules, llm 포함)
            skills: SkillCatalog - 현재 Agent가 수행 가능한 skills/actions
        """
        self.agent_config = agent_config
        self.skills = skills
        self.llm_enabled = agent_config.get("llm", {}).get("enabled", False)
        self.llm_client = None

        # LLM 클라이언트 초기화 (Ollama, Claude 등)
        if self.llm_enabled and make_llm_client:
            try:
                self.llm_client = make_llm_client(agent_config.get("llm", {}))
            except Exception as e:
                logger.error(f"LLM 클라이언트 초기화 실패: {e}")
                self.llm_enabled = False

    def decide(self, state: AgentState, telemetry: dict[str, Any]) -> dict[str, Any]:
        """
        현재 상태와 텔레메트리를 기반으로 의사결정 수행

        Process:
        1. 현재 Agent가 수행 가능한 actions 확인
        2. Config의 rules 읽기 (battery_warn_percent, max_speed_mps 등)
        3. Telemetry에서 현재 상태 추출 (speed, battery 등)
        4. Rule 기반 권장사항 생성 (동기 실행)
        5. LLM 분석 시작 (비동기, 다음 iteration 블로킹 없음)
        6. Decision 반환

        Args:
            state: Agent의 현재 상태
            telemetry: 현재 센서/상태 데이터

        Returns:
            dict: Decision 객체
                {
                  "at": 시각,
                  "mode": "rule",
                  "llm_enabled": LLM 활성화 여부,
                  "recommendations": [규칙 기반 권장사항들],
                  "llm_analysis": LLM 분석 결과 (비동기로 나중에 업데이트됨)
                }
        """
        # 현재 Agent가 수행 가능한 모든 actions 목록
        actions = set(self.skills.list_actions())

        # Config에서 규칙 읽기
        rules = self.agent_config.get("rules", {})
        battery_warn = float(rules.get("battery_warn_percent", 30))  # 배터리 경고 임계값 (%)
        max_speed = float(rules.get("max_speed_mps", 999))  # 최대 속도 (m/s)

        # 현재 텔레메트리에서 상태 추출
        speed = float((telemetry.get("motion") or {}).get("speed") or 0)  # 현재 속도 (m/s)
        battery = float(telemetry.get("battery_percent") or 100)  # 현재 배터리 (%)
        recommendations: list[dict[str, Any]] = []

        # ===== Rule 기반 의사결정 (동기 실행) =====

        # 규칙 1: 속도 제한 - 최대 속도 초과 시 감속
        if "slow_down" in actions and speed > max_speed:
            recommendations.append({
                "action": "slow_down",
                "priority": "high",
                "confidence": 0.95,  # 규칙 기반이므로 높은 신뢰도
                "source": "rule",
                "params": {"target_speed_mps": max_speed},
            })

        # 규칙 2: 배터리 부족 - 임계값 이하 시 기지 복귀
        if "return_to_base" in actions and battery < battery_warn:
            recommendations.append({
                "action": "return_to_base",
                "priority": "high",
                "confidence": 0.95,
                "source": "rule",
                "params": {"battery_percent": battery},
            })

        # 규칙 3: 자식 조율 - Middle Agent인 경우 자식 agents 조율
        if state.layer == "middle" and state.children:
            recommendations.append({
                "action": "coordinate_children",
                "priority": "normal",
                "confidence": 0.8,
                "source": "rule",
                "params": {"child_count": len(state.children)},
            })

        # Decision 객체 생성
        decision = {
            "at": utc_now(),
            "mode": "rule",
            "llm_enabled": self.llm_enabled,
            "recommendations": recommendations,
            "llm_analysis": None,  # 비동기 LLM이 나중에 업데이트함
        }

        # ===== LLM 분석 (비동기, 논블로킹) =====
        # LLM 호출이 simulation loop를 블로킹하지 않도록 백그라운드 task로 실행
        if self.llm_enabled and self.llm_client and recommendations:
            asyncio.create_task(self._analyze_with_llm(state, telemetry, recommendations, decision))

        # Agent 상태에 최신 decision 저장
        state.last_decision = decision
        return decision

    async def _analyze_with_llm(
        self,
        state: AgentState,
        telemetry: dict[str, Any],
        rule_recs: list[dict[str, Any]],
        decision: dict[str, Any],
    ) -> None:
        """
        LLM을 사용하여 상황을 분석하고 추가 인사이트 제공 (비동기)

        이 메서드는 simulation_loop을 블로킹하지 않도록 백그라운드에서 실행됩니다.
        LLM 호출이 오래 걸려도 다음 iteration을 진행할 수 있습니다.

        Args:
            state: Agent 상태
            telemetry: 센서 데이터
            rule_recs: Rule 기반 권장사항들
            decision: Decision 객체 (LLM 분석 결과로 업데이트됨)
        """
        try:
            # LLM용 프롬프트 생성
            prompt = self._build_llm_prompt(state, telemetry, rule_recs)
            timeout = self.agent_config.get("llm", {}).get("timeout_seconds", 30)

            # LLM 호출 (await를 사용하여 응답 대기, 하지만 다른 tasks는 진행 가능)
            response = await self.llm_client.generate(prompt=prompt, timeout=timeout)

            # LLM 분석 결과를 decision에 업데이트
            decision["llm_analysis"] = {
                "timestamp": utc_now(),
                "response": response[:200] if response else "응답 없음",
                "source": "llm",
            }
            logger.debug(f"LLM 분석 완료: {response[:100]}...")
        except Exception as e:
            # LLM 호출 실패해도 rule 기반 decision이 있으므로 시스템 계속 작동
            logger.debug(f"LLM 분석 오류: {e}")
            decision["llm_analysis"] = {"error": str(e), "timestamp": utc_now()}

    def _build_llm_prompt(self, state: AgentState, telemetry: dict[str, Any], rule_recs: list[dict[str, Any]]) -> str:
        """
        현재 상황을 설명하는 LLM 프롬프트 생성

        Args:
            state: Agent 상태 (device_type, layer 등)
            telemetry: 센서 데이터
            rule_recs: Rule 기반 권장사항들

        Returns:
            str: LLM에 보낼 프롬프트
        """
        return f"""당신은 {state.device_type} 에이전트이며 {state.layer} 계층에서 운영 중입니다.

현재 상태:
- 장치: {state.agent_id}
- 배터리: {telemetry.get('battery_percent', 'unknown')}%
- 계층: {state.layer}

텔레메트리 요약:
- 속도: {(telemetry.get('motion') or {}).get('speed', 0)} m/s
- 배터리: {telemetry.get('battery_percent', 100)}%

규칙 기반 권장사항:
{json.dumps(rule_recs, indent=2, ensure_ascii=False)}

간단히 분석해주세요: 이상 징후가 있나요? 추가로 권장할 사항이 있나요? 100자 이내로 답변해주세요."""
