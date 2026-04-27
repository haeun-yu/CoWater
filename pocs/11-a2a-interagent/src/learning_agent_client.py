#!/usr/bin/env python3
"""
A2A Learning Agent Client

Learning Agent가 Detection Agent에게 rule update를 제안하는
A2A Task를 전송하고 결과를 확인합니다.

시나리오:
1. Detection Agent의 Agent Card 조회 (capability discovery)
2. 시뮬레이션: FP rate 높음 감지
3. Learning Agent → Detection Agent에게 Task 전송 (high confidence)
4. 결과 확인: 임계값이 즉시 적용됨
5. 두 번째 Task (low confidence → pending 처리)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

# ─────────────────────────────────────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [A2A Learning Agent] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


def print_section(title: str, char: str = "="):
    """섹션 구분선 출력"""
    width = 70
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}\n")


def format_json(data: Any, indent: int = 2) -> str:
    """JSON 예쁜 출력"""
    return json.dumps(data, ensure_ascii=False, indent=indent)


# ─────────────────────────────────────────────────────────────────────────────
# A2A Task 전송/조회
# ─────────────────────────────────────────────────────────────────────────────


def get_agent_card(base_url: str) -> dict:
    """
    Detection Agent의 Agent Card 조회

    이를 통해 에이전트의 capability를 discovery합니다.
    """
    logger.info(f"[1] Discovering Detection Agent: GET {base_url}/.well-known/agent.json")

    response = httpx.get(f"{base_url}/.well-known/agent.json", timeout=10.0)
    response.raise_for_status()

    card = response.json()

    print(f"\n✓ Agent Card Retrieved")
    print(f"  Name: {card['name']}")
    print(f"  Display Name: {card['displayName']}")
    print(f"  Version: {card['version']}")
    print(f"  API Version: {card.get('apiVersion', 'N/A')}")
    print(f"  Capabilities: {format_json(card['capabilities'])}")
    print(f"\n  Skills:")
    for skill in card["skills"]:
        print(f"    - {skill['id']}: {skill['name']}")
        print(f"      {skill['description']}")

    return card


def send_task(base_url: str, payload: dict) -> dict:
    """
    A2A Task 전송

    POST /tasks/send에 rule update 제안을 전송하고,
    서버는 신뢰도 판단 후 즉시 처리 결과를 반환합니다.
    """
    logger.info(f"[2] Sending A2A Task: POST {base_url}/tasks/send")

    response = httpx.post(f"{base_url}/tasks/send", json=payload, timeout=10.0)
    response.raise_for_status()

    task = response.json()

    print(f"\n✓ Task Sent and Processed")
    print(f"  Task ID: {task['id']}")
    print(f"  Status: {task['status']['state']}")

    return task


def query_task(base_url: str, task_id: str) -> dict:
    """
    A2A Task 조회

    비동기 작업의 경우 GET /tasks/{task_id}로 폴링합니다.
    이 POC에서는 send_task가 이미 동기 처리하므로, 확인 차원입니다.
    """
    logger.info(f"[3] Querying Task: GET {base_url}/tasks/{task_id}")

    response = httpx.get(f"{base_url}/tasks/{task_id}", timeout=10.0)
    response.raise_for_status()

    task = response.json()

    print(f"\n✓ Task Status")
    print(f"  Task ID: {task['id']}")
    print(f"  Status: {task['status']['state']}")

    return task


# ─────────────────────────────────────────────────────────────────────────────
# POC 시나리오
# ─────────────────────────────────────────────────────────────────────────────


def run_scenario_1_high_confidence(base_url: str):
    """
    시나리오 1: CPA FP rate 높음 → rule 즉시 조정

    Learning Agent 분석:
    - 24시간 동안 CPA agent가 45건 탐지 중 15건 오탐지 (FP rate: 33.3%)
    - CPA critical threshold 0.5 NM은 너무 낮음
    - 제안: 0.5 NM → 1.0 NM 상향
    - 신뢰도: 0.72 (높음) → 즉시 적용
    """
    print_section("시나리오 1: CPA Rule 조정 (High Confidence)", "─")

    print("상황 분석:")
    print("  - Detection: CPA agent")
    print("  - 기간: 최근 24시간")
    print("  - 탐지: 45건, 오탐지(FP): 15건 (33.3%)")
    print("  - 원인: critical_cpa_nm = 0.5 NM이 너무 낮음")
    print("  - 처방: threshold 상향 (0.5 → 1.0 NM)")
    print("  - 신뢰도: 0.72 (높음) → 즉시 적용 가능")

    payload = {
        "skill_id": "suggest_rule_update",
        "message": {
            "role": "user",
            "parts": [
                {
                    "type": "data",
                    "data": {
                        "target_agent_id": "detection-cpa",
                        "old_config": {
                            "critical_cpa_nm": 0.5,
                        },
                        "new_config": {
                            "critical_cpa_nm": 1.0,
                        },
                        "reason": (
                            "최근 24시간 CPA critical FP rate 33.3% (15/45) — "
                            "critical threshold 상향으로 오탐지 감소 가능"
                        ),
                        "confidence": 0.72,
                        "fp_rate": 0.333,
                        "sample_count": 45,
                        "improved_fp_rate_expected": 0.15,
                        "requested_by": "learning-agent",
                        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
            ],
        },
    }

    task = send_task(base_url, payload)

    # artifacts에서 결과 읽기
    print("\n[4] 결과 분석")

    if task.get("artifacts"):
        for artifact in task["artifacts"]:
            if artifact["name"] == "rule_update_result":
                result = artifact["parts"][0]["data"]

                print(f"\n  ✓ 규칙 업데이트 결과:")
                print(f"    대상 Agent: {result['target_agent_id']}")
                print(f"    신뢰도: {result['confidence']:.2f}")
                print(f"    처리 시각: {result['processed_at']}")

                if result.get("applied_changes"):
                    print(f"\n    ✅ 즉시 적용된 변경:")
                    for param, change in result["applied_changes"].items():
                        print(
                            f"      • {param}: {change['from']} → {change['to']} "
                            f"(confidence {change['confidence']:.2f})"
                        )

                if result.get("pending_changes"):
                    print(f"\n    ⏸ 보류된 변경:")
                    for param, change in result["pending_changes"].items():
                        print(
                            f"      • {param}: {change['current']} → {change['proposed']} "
                            f"(신뢰도 {change['confidence']:.2f} < 0.6)"
                        )

                print(f"\n    📊 현재 설정 (업데이트됨):")
                print(f"      {format_json(result['current_config'])}")

            elif artifact["name"] == "error":
                error = artifact["parts"][0]["data"]
                print(f"\n  ✗ 오류: {error['error']}")


def run_scenario_2_low_confidence(base_url: str):
    """
    시나리오 2: Anomaly ROT threshold 조정 (Low Confidence)

    Learning Agent 분석:
    - Anomaly agent의 ROT (Rate of Turn) threshold 20°/min은 조정 가능
    - 제안: 20°/min → 30°/min
    - 신뢰도: 0.45 (낮음) → 보류 처리 (관제사 수동 검토 필요)
    """
    print_section("시나리오 2: Anomaly Rule 조정 (Low Confidence)", "─")

    print("상황 분석:")
    print("  - Detection: Anomaly agent")
    print("  - 파라미터: rot_threshold (Rate of Turn)")
    print("  - 현재값: 20°/min")
    print("  - 제안값: 30°/min (더 큰 회전만 이상으로 감지)")
    print("  - 신뢰도: 0.45 (낮음) → 즉시 적용 불가")
    print("  - 처리: pending 상태로 보류 (관제사 수동 승인 필요)")

    payload = {
        "skill_id": "suggest_rule_update",
        "message": {
            "role": "user",
            "parts": [
                {
                    "type": "data",
                    "data": {
                        "target_agent_id": "detection-anomaly",
                        "new_config": {
                            "rot_threshold": 30.0,
                        },
                        "reason": (
                            "ROT anomaly detection 패턴 분석 — "
                            "threshold 상향으로 정상 회전 오탐지 감소 가능성 있으나 "
                            "충분한 표본 부족"
                        ),
                        "confidence": 0.45,
                        "sample_count": 12,
                        "requested_by": "learning-agent",
                        "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                }
            ],
        },
    }

    task = send_task(base_url, payload)

    # artifacts에서 결과 읽기
    print("\n[4] 결과 분석")

    if task.get("artifacts"):
        for artifact in task["artifacts"]:
            if artifact["name"] == "rule_update_result":
                result = artifact["parts"][0]["data"]

                print(f"\n  ⏸ 규칙 업데이트 결과:")
                print(f"    대상 Agent: {result['target_agent_id']}")
                print(f"    신뢰도: {result['confidence']:.2f}")
                print(f"    처리 시각: {result['processed_at']}")

                if result.get("applied_changes"):
                    print(f"\n    ✅ 즉시 적용된 변경:")
                    for param, change in result["applied_changes"].items():
                        print(
                            f"      • {param}: {change['from']} → {change['to']}"
                        )
                else:
                    print(f"\n    ✅ 즉시 적용된 변경: (없음)")

                if result.get("pending_changes"):
                    print(f"\n    ⏸ 보류된 변경:")
                    for param, change in result["pending_changes"].items():
                        print(
                            f"      • {param}: {change['current']} → {change['proposed']}"
                        )
                        print(
                            f"        사유: {change['reason']} "
                            f"(신뢰도 {change['confidence']:.2f} < 0.6)"
                        )
                        print(f"        👉 관제사 수동 검토 필요")

                print(f"\n    📊 현재 설정:")
                print(f"      {format_json(result['current_config'])}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Main entry point"""
    detection_agent_url = os.getenv(
        "DETECTION_AGENT_URL", "http://detection-agent:8001"
    )

    print_section(
        "CoWater A2A Inter-Agent Protocol POC — Learning ↔ Detection",
        "═",
    )

    print(f"Detection Agent URL: {detection_agent_url}")
    print(f"Protocol: Google A2A (2025-04)")

    try:
        # Step 1: Agent Card 조회
        card = get_agent_card(detection_agent_url)

        # Step 2-4: 시나리오 1 (High Confidence)
        run_scenario_1_high_confidence(detection_agent_url)

        # Step 2-4: 시나리오 2 (Low Confidence)
        run_scenario_2_low_confidence(detection_agent_url)

        # 최종 요약
        print_section("요약", "─")

        print("✅ A2A 통신 성공")
        print("\nA2A 워크플로우:")
        print("  1. Learning Agent가 Detection Agent의 Agent Card 조회")
        print("     → Capability discovery (지원하는 skill 확인)")
        print("")
        print("  2. Learning Agent가 rule update Task 생성 + 전송")
        print("     POST /tasks/send → Task ID, status, payload 포함")
        print("")
        print("  3. Detection Agent가 신뢰도 판단:")
        print("     confidence >= 0.6 → 즉시 적용 (applied_changes)")
        print("     confidence < 0.6  → 보류 처리 (pending_changes)")
        print("")
        print("  4. Learning Agent가 artifacts에서 결과 확인")
        print("     GET /tasks/{task_id} 또는 POST 응답")
        print("")

        print("이점:")
        print("  • 표준 A2A 프로토콜 사용 → 타사 에이전트와 상호운용 가능")
        print("  • JSON 기반 → 언어/플랫폼 독립적")
        print("  • Agent Card로 capability 사전 discovery")
        print("  • 신뢰도 기반 자동/수동 처리 분기")
        print("  • Artifacts로 상세한 처리 결과 반환")
        print("")

        print("🎯 POC 목표 달성: Detection ↔ Learning 간 표준 A2A 통신 검증")

    except KeyboardInterrupt:
        logger.info("\nPOC interrupted by user")
    except Exception as e:
        logger.exception(f"POC failed: {e}")
        sys.exit(1)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
