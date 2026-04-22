#!/usr/bin/env python3
"""
MCP Detection Server — Detection rules를 MCP Tool로 노출합니다.

FastMCP + streamable-http transport를 사용하여:
1. get_detection_rules(agent_type) — Detection agent 설정 반환
2. compute_cpa(platform_a, platform_b) — CPA/TCPA 계산
3. check_zone_breach(platform, zones) — 구역 침범 확인

http://localhost:8000 에서 streamable-http로 수신.
"""

import math
from mcp.server.fastmcp import FastMCP

# ─────────────────────────────────────────────────────────────────────────────
# Mock 설정 데이터 (services/detection-agents/config.py 참고)
# ─────────────────────────────────────────────────────────────────────────────

AGENT_RULES = {
    "cpa": {
        "warning_cpa_nm": 2.0,
        "warning_tcpa_min": 20.0,
        "critical_cpa_nm": 0.5,
        "critical_tcpa_min": 10.0,
        "skip_nav_statuses": ["at_anchor", "moored", "aground"],
        "max_report_age_sec": 300,
    },
    "anomaly": {
        "ais_timeout_sec": 90,
        "speed_drop_threshold": 5.0,
        "rot_threshold": 20.0,
        "heading_threshold": 45.0,
        "position_jump_threshold_nm": 5.0,
    },
    "zone": {
        "alert_types": ["prohibited", "restricted"],
        "state_ttl_sec": 3600,
    },
    "distress": {
        "monitored_patterns": ["SECURITE", "PAN_PAN", "MAYDAY"],
        "alert_severity": "critical",
    },
    "mine": {
        "confidence_threshold": 0.7,
        "emit_cooldown_sec": 300,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# FastMCP 서버 초기화
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP("cowater-detection")


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tools
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_detection_rules(agent_type: str) -> dict:
    """
    Detection agent의 규칙 설정을 조회합니다.

    Args:
        agent_type: Detection agent 타입
                   ('cpa' | 'anomaly' | 'zone' | 'distress' | 'mine')

    Returns:
        규칙 설정 딕셔너리 또는 에러
    """
    if agent_type not in AGENT_RULES:
        return {
            "error": f"Unknown agent type: {agent_type}",
            "valid_types": list(AGENT_RULES.keys()),
        }

    return {
        "agent_type": agent_type,
        "rules": AGENT_RULES[agent_type],
        "description": _get_agent_description(agent_type),
    }


@mcp.tool()
def compute_cpa(
    platform_a: dict,
    platform_b: dict,
) -> dict:
    """
    두 플랫폼 간 CPA(Closest Point of Approach, NM)와
    TCPA(Time to Closest Point of Approach, 분)을 계산합니다.

    Args:
        platform_a: {"lat": float, "lon": float, "sog": float, "cog": float, "platform_id": str}
        platform_b: {"lat": float, "lon": float, "sog": float, "cog": float, "platform_id": str}

    Returns:
        CPA 정보:
        {
            "cpa_nm": float,           # 최근접거리 (해리)
            "tcpa_min": float | None,  # 최근접시간 (분)
            "converging": bool,        # 수렴 중인지 여부
            "severity": str,           # "critical" | "warning" | "safe"
        }
    """
    try:
        NM_PER_DEG_LAT = 60.0
        KNOTS_TO_NM_PER_MIN = 1 / 60.0

        # 두 플랫폼 간 상대 위치 (해리 단위)
        avg_lat = (platform_a["lat"] + platform_b["lat"]) / 2
        cos_lat = math.cos(math.radians(avg_lat))

        dx = (platform_b["lon"] - platform_a["lon"]) * cos_lat * NM_PER_DEG_LAT
        dy = (platform_b["lat"] - platform_a["lat"]) * NM_PER_DEG_LAT

        # 두 플랫폼의 속도 벡터 변환 (COG, SOG → 동/북 성분)
        def velocity_components(sog: float, cog: float) -> tuple:
            cog_rad = math.radians(cog)
            vx = sog * math.sin(cog_rad) * KNOTS_TO_NM_PER_MIN
            vy = sog * math.cos(cog_rad) * KNOTS_TO_NM_PER_MIN
            return vx, vy

        vx1, vy1 = velocity_components(platform_a["sog"], platform_a["cog"])
        vx2, vy2 = velocity_components(platform_b["sog"], platform_b["cog"])

        # 상대 속도
        dvx = vx2 - vx1
        dvy = vy2 - vy1
        dv2 = dvx**2 + dvy**2

        # 두 플랫폼이 정지 중이거나 같은 속도면 현재 거리가 CPA
        if dv2 < 1e-9:
            cpa_nm = math.hypot(dx, dy)
            return {
                "cpa_nm": round(cpa_nm, 3),
                "tcpa_min": None,
                "converging": False,
                "severity": "safe",
            }

        # TCPA 계산 (최근접까지의 시간)
        tcpa_min = -((dx * dvx) + (dy * dvy)) / dv2

        # TCPA일 때의 거리 (CPA)
        cpa_x = dx + dvx * tcpa_min
        cpa_y = dy + dvy * tcpa_min
        cpa_nm = math.hypot(cpa_x, cpa_y)

        # Severity 판정 (AGENT_RULES의 임계값 기준)
        rules = AGENT_RULES["cpa"]
        if (
            cpa_nm < rules["critical_cpa_nm"]
            and tcpa_min < rules["critical_tcpa_min"]
        ):
            severity = "critical"
        elif (
            cpa_nm < rules["warning_cpa_nm"]
            and tcpa_min < rules["warning_tcpa_min"]
        ):
            severity = "warning"
        else:
            severity = "safe"

        return {
            "cpa_nm": round(cpa_nm, 3),
            "tcpa_min": round(tcpa_min, 2),
            "converging": tcpa_min > 0,
            "severity": severity,
            "platform_a_id": platform_a.get("platform_id", "unknown"),
            "platform_b_id": platform_b.get("platform_id", "unknown"),
        }

    except Exception as e:
        return {"error": f"CPA computation failed: {str(e)}"}


@mcp.tool()
def check_zone_breach(platform: dict, zones: list) -> dict:
    """
    선박이 제한/금지 구역을 침범했는지 확인합니다.

    Args:
        platform: {"lat": float, "lon": float, "platform_id": str}
        zones: [
            {
                "zone_id": str,
                "zone_type": "prohibited" | "restricted",
                "center_lat": float,
                "center_lon": float,
                "radius_nm": float,
            }
        ]

    Returns:
        구역 침범 결과:
        {
            "platform_id": str,
            "breach_count": int,
            "breaches": [
                {
                    "zone_id": str,
                    "zone_type": str,
                    "distance_nm": float,
                    "severity": "critical" | "warning",
                }
            ],
        }
    """
    try:
        NM_PER_DEG = 60.0
        breaches = []

        for zone in zones:
            # zone_type 유효성 확인
            if zone.get("zone_type") not in ("prohibited", "restricted"):
                continue

            # 선박과 구역 중심 간 거리 계산 (해리)
            dlat = (platform["lat"] - zone["center_lat"]) * NM_PER_DEG
            dlon = (platform["lon"] - zone["center_lon"]) * NM_PER_DEG * math.cos(
                math.radians(platform["lat"])
            )
            dist_nm = math.hypot(dlat, dlon)

            # 구역 반경 내 여부 확인
            radius_nm = zone.get("radius_nm", 1.0)
            if dist_nm <= radius_nm:
                severity = (
                    "critical"
                    if zone["zone_type"] == "prohibited"
                    else "warning"
                )
                breaches.append(
                    {
                        "zone_id": zone["zone_id"],
                        "zone_type": zone["zone_type"],
                        "distance_nm": round(dist_nm, 3),
                        "severity": severity,
                    }
                )

        return {
            "platform_id": platform.get("platform_id", "unknown"),
            "breach_count": len(breaches),
            "breaches": breaches,
        }

    except Exception as e:
        return {"error": f"Zone breach check failed: {str(e)}"}


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────


def _get_agent_description(agent_type: str) -> str:
    """Agent 타입별 설명"""
    descriptions = {
        "cpa": "충돌 회피(CPA/TCPA) 탐지 — 두 선박 간 최근접거리 임계값 기반",
        "anomaly": "이상 행동 탐지 — AIS 신호 손실, 급격한 속도/침로 변화",
        "zone": "구역 침범 탐지 — 금지/제한 구역 위반",
        "distress": "조난 신호 탐지 — SECURITE, PAN_PAN, MAYDAY 음성 신호",
        "mine": "지뢰 탐지 — 소나 센서 기반 의심 접촉",
    }
    return descriptions.get(agent_type, "Unknown agent type")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [MCP Server] %(message)s",
    )
    logger = logging.getLogger(__name__)

    logger.info("Starting MCP Detection Server on 0.0.0.0:8000...")
    logger.info("Transport: streamable-http")
    logger.info("Tools: get_detection_rules, compute_cpa, check_zone_breach")

    # FastMCP streamable-http 서버 시작
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
