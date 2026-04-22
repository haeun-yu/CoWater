#!/usr/bin/env python3
"""
MCP Detection Client — Claude를 통한 해양관제 분석

MCP 서버에 정의된 detection tools를 통해 Claude가 tool_use로
선박 현황을 분석하고 위험도를 판정합니다.

Agentic loop:
1. Claude에 선박 데이터 전달
2. Claude가 tool_use를 시도 (get_detection_rules, compute_cpa, check_zone_breach)
3. MCP 서버에서 tool 실행 결과 받음
4. Claude에게 결과 반환 → 최종 분석 생성
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

import httpx

import anthropic

# ─────────────────────────────────────────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MCP Client] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Mock 시나리오 데이터
# ─────────────────────────────────────────────────────────────────────────────

MOCK_SCENARIO = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "platforms": [
        {
            "platform_id": "VESSEL-001",
            "name": "화물선 A (Cargo Vessel A)",
            "lat": 35.10,
            "lon": 129.05,
            "sog": 12.0,
            "cog": 45.0,
            "nav_status": "under_way",
            "mmsi": "1234567890",
        },
        {
            "platform_id": "VESSEL-002",
            "name": "화물선 B (Cargo Vessel B)",
            "lat": 35.12,
            "lon": 129.07,
            "sog": 10.0,
            "cog": 225.0,
            "nav_status": "under_way",
            "mmsi": "9876543210",
        },
    ],
    "zones": [
        {
            "zone_id": "zone-001",
            "zone_name": "부산항 금지구역 A (Busan Port Prohibited Zone A)",
            "zone_type": "prohibited",
            "center_lat": 35.11,
            "center_lon": 129.06,
            "radius_nm": 0.5,
        },
        {
            "zone_id": "zone-002",
            "zone_name": "해군 기동 훈련 구역 (Naval Exercise Zone)",
            "zone_type": "restricted",
            "center_lat": 35.15,
            "center_lon": 129.10,
            "radius_nm": 2.0,
        },
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Claude Tool 정의 (anthropic SDK tools 파라미터 포맷)
# ─────────────────────────────────────────────────────────────────────────────

MCP_TOOLS = [
    {
        "name": "get_detection_rules",
        "description": (
            "Detection agent의 규칙 설정(임계값, 파라미터)을 조회합니다. "
            "agent_type으로 특정 agent의 규칙을 반환하거나, 지원하는 타입 목록을 제시합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "description": "Detection agent 타입: cpa, anomaly, zone, distress, mine",
                    "enum": ["cpa", "anomaly", "zone", "distress", "mine"],
                },
            },
            "required": ["agent_type"],
        },
    },
    {
        "name": "compute_cpa",
        "description": (
            "두 선박 간 CPA(Closest Point of Approach, 해리)와 "
            "TCPA(Time to Closest Point of Approach, 분)를 계산합니다. "
            "충돌 위험도를 판정하는 데 사용됩니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "platform_a": {
                    "type": "object",
                    "description": "첫 번째 플랫폼 정보",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "sog": {"type": "number", "description": "속력 (knots)"},
                        "cog": {"type": "number", "description": "침로 (degrees)"},
                        "platform_id": {"type": "string"},
                    },
                    "required": ["lat", "lon", "sog", "cog"],
                },
                "platform_b": {
                    "type": "object",
                    "description": "두 번째 플랫폼 정보",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "sog": {"type": "number"},
                        "cog": {"type": "number"},
                        "platform_id": {"type": "string"},
                    },
                    "required": ["lat", "lon", "sog", "cog"],
                },
            },
            "required": ["platform_a", "platform_b"],
        },
    },
    {
        "name": "check_zone_breach",
        "description": (
            "선박이 제한/금지 구역을 침범했는지 확인합니다. "
            "구역 내 거리와 심각도를 반환합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "object",
                    "description": "확인할 플랫폼 정보",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"},
                        "platform_id": {"type": "string"},
                    },
                    "required": ["lat", "lon"],
                },
                "zones": {
                    "type": "array",
                    "description": "구역 정보 목록",
                    "items": {
                        "type": "object",
                        "properties": {
                            "zone_id": {"type": "string"},
                            "zone_type": {
                                "type": "string",
                                "enum": ["prohibited", "restricted"],
                            },
                            "center_lat": {"type": "number"},
                            "center_lon": {"type": "number"},
                            "radius_nm": {"type": "number"},
                        },
                        "required": [
                            "zone_id",
                            "zone_type",
                            "center_lat",
                            "center_lon",
                        ],
                    },
                },
            },
            "required": ["platform", "zones"],
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool 호출 (HTTP via streamable-http)
# ─────────────────────────────────────────────────────────────────────────────


def call_mcp_tool(tool_name: str, tool_input: dict, mcp_base_url: str) -> str:
    """
    MCP 서버의 tool을 HTTP로 호출합니다.

    streamable-http transport는 /mcp/ 엔드포인트에서
    JSON-RPC 2.0 포맷의 요청을 수신합니다.

    Args:
        tool_name: Tool 이름
        tool_input: Tool 입력 파라미터
        mcp_base_url: MCP 서버 URL (e.g., http://mcp-server:8000)

    Returns:
        Tool 실행 결과 (JSON 문자열)
    """
    try:
        # JSON-RPC 2.0 페이로드
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": tool_input,
            },
            "id": str(uuid4()),
        }

        logger.debug(f"Calling MCP tool: {tool_name}")

        with httpx.Client(timeout=30.0) as client:
            response = client.post(f"{mcp_base_url}/mcp/", json=payload)
            response.raise_for_status()

        result = response.json()

        # streamable-http 응답 파싱
        if "result" in result:
            content = result["result"].get("content", [{}])
            if content and "text" in content[0]:
                return content[0]["text"]
            return json.dumps(result["result"])

        logger.warning(f"Unexpected MCP response: {result}")
        return json.dumps(result)

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling MCP tool: {e}")
        return json.dumps({"error": f"HTTP error: {str(e)}"})
    except Exception as e:
        logger.error(f"Error calling MCP tool: {e}")
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────────────────────────────────────
# Claude Agentic Loop
# ─────────────────────────────────────────────────────────────────────────────


def run_analysis(mcp_base_url: str, api_key: str):
    """
    Claude와 MCP를 활용한 해양관제 분석 실행

    Agentic loop:
    1. Claude에게 선박 현황 전달
    2. Claude가 필요한 tool을 호출 (stop_reason == "tool_use")
    3. MCP 서버에서 tool 실행
    4. 결과를 Claude에게 반환
    5. 최종 분석 생성 (stop_reason == "end_turn")
    """
    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = """당신은 연안 VTS(선박교통서비스) 해양 관제 AI입니다.
제공된 실시간 선박 데이터를 분석하여 충돌 위험, 구역 침범, 이상 행동을 탐지합니다.

분석 절차:
1. get_detection_rules를 호출하여 현재 적용 중인 rule을 확인하세요.
2. compute_cpa를 호출하여 선박 간 충돌 위험을 계산하세요.
3. check_zone_breach를 호출하여 구역 침범을 확인하세요.
4. 종합 분석 결과와 권고사항을 작성하세요.

분석 결과는:
- 심각도 (critical/warning/info)
- 관련 선박/구역
- 권고 조치
를 포함해야 합니다."""

    # 사용자 메시지: 선박 현황 + 분석 요청
    user_message = f"""다음 선박 현황을 실시간으로 분석해주세요:

=== 현재 시각 ===
{MOCK_SCENARIO["timestamp"]}

=== 감시 중인 선박 목록 ===
{json.dumps(MOCK_SCENARIO["platforms"], ensure_ascii=False, indent=2)}

=== 관제 구역 ===
{json.dumps(MOCK_SCENARIO["zones"], ensure_ascii=False, indent=2)}

=== 분석 요청 ===
1. CPA detection rule 조회 후, 모든 선박 쌍에 대해 충돌 위험(CPA/TCPA)을 계산하세요.
2. Zone detection rule 조회 후, 모든 선박의 구역 침범 여부를 확인하세요.
3. 각 선박별 리스크 평가 및 권고사항을 작성하세요.
4. 즉시 조치가 필요한 항목(critical)이 있으면 강조하세요."""

    messages = [{"role": "user", "content": user_message}]

    logger.info("Starting Claude analysis with MCP tools...")
    logger.info(f"MCP Server: {mcp_base_url}")

    iteration = 0
    max_iterations = 10  # 무한 loop 방지

    # Agentic loop
    while iteration < max_iterations:
        iteration += 1
        logger.info(f"\n--- Iteration {iteration} ---")

        # Claude API 호출
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=system_prompt,
            tools=MCP_TOOLS,
            messages=messages,
        )

        logger.debug(f"Stop reason: {response.stop_reason}")

        # Tool use 처리
        if response.stop_reason == "tool_use":
            # Assistant 응답을 메시지에 추가
            messages.append({"role": "assistant", "content": response.content})

            # Tool use 블록 처리
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"[Tool Call] {block.name}")
                    logger.debug(f"  Input: {json.dumps(block.input, indent=2)}")

                    # MCP 서버에서 tool 실행
                    result_text = call_mcp_tool(
                        block.name, block.input, mcp_base_url
                    )

                    logger.info(f"[Tool Result] {block.name}")
                    logger.debug(f"  Output: {result_text[:200]}...")

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        }
                    )

            # Tool 결과를 사용자 메시지로 추가
            messages.append({"role": "user", "content": tool_results})

        # 최종 응답 (end_turn)
        elif response.stop_reason == "end_turn":
            logger.info("\n=== Claude 최종 분석 결과 ===\n")

            for block in response.content:
                if hasattr(block, "text"):
                    print(block.text)
                    print()

            break

        # 기타 stop_reason
        else:
            logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
            break

    if iteration >= max_iterations:
        logger.warning(f"Max iterations ({max_iterations}) reached")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Main entry point"""
    mcp_server_url = os.getenv("MCP_SERVER_URL", "http://mcp-server:8000")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    logger.info("=" * 70)
    logger.info("CoWater MCP Detection Client - Analysis with Claude Tool Use")
    logger.info("=" * 70)

    try:
        run_analysis(mcp_server_url, anthropic_api_key)
    except KeyboardInterrupt:
        logger.info("\nAnalysis interrupted by user")
    except Exception as e:
        logger.exception(f"Analysis failed: {e}")
        sys.exit(1)

    logger.info("\n" + "=" * 70)
    logger.info("Analysis complete")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
