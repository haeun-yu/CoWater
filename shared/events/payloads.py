"""
Event Payload 타입 정의.

각 Event 타입별로 payload의 구조를 명확히 정의.
- 필수 필드: Event를 처리하기 위한 최소 정보
- 선택 필드: fallback으로 처리 가능 (API 호출로 보충 가능)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DetectCPAPayload:
    """
    CPA(Closest Point of Approach) 위험 감지 이벤트.

    필수: 두 선박의 현재 위치 및 속력 벡터
    선택: 선박 이력, 구역 정보
    """

    # ─ 필수 필드
    platform_id: str
    target_platform_id: str
    cpa_minutes: float  # 최근 시점까지의 거리 (분)
    tcpa_minutes: float  # 최근 시점까지의 시간 (분)
    latitude: float
    longitude: float
    platform_name: str
    target_name: str
    platform_sog: Optional[float]  # knots
    platform_cog: Optional[float]  # degrees
    target_sog: Optional[float]
    target_cog: Optional[float]

    # ─ 선택 필드 (API로 보충 가능)
    platform_history: Optional[list[dict]] = None  # 최근 10개 위치
    zone_context: Optional[dict] = None  # 현재 구역 정보


@dataclass
class DetectAnomalyPayload:
    """
    비정상 항적 감지 (ROT, heading 급변화, 속도 급증 등).

    필수: 현재 위치 + 비정상 타입
    선택: 항적 이력, 주변 선박, 기상 정보
    """

    # ─ 필수 필드
    platform_id: str
    platform_name: str
    anomaly_type: str  # "rot" | "heading_jump" | "speed_spike" | "position_jump"
    anomaly_value: float  # ROT의 경우 °/min, heading의 경우 degrees
    latitude: float
    longitude: float
    timestamp: datetime

    # ─ 선택 필드
    platform_history: Optional[list[dict]] = None  # 최근 20개 점
    nearby_platforms: Optional[list[dict]] = None
    weather_data: Optional[dict] = None
    voyage_plan: Optional[dict] = None


@dataclass
class DetectZonePayload:
    """
    구역 침입/이탈 감지.

    필수: 선박 위치 + 구역 정보
    선택: 구역 geometry (intrusion 판단이 이미 되었으므로 선택)
    """

    # ─ 필수 필드
    platform_id: str
    platform_name: str
    zone_id: str
    zone_name: str
    zone_type: str  # "prohibited" | "restricted" | "fairway" | ...
    latitude: float
    longitude: float
    timestamp: datetime
    event_type: str  # "intrusion" | "exit"

    # ─ 선택 필드
    zone_geometry: Optional[dict] = None  # GeoJSON (이미 판단됨)
    dwell_seconds: Optional[float] = None  # zone_exit인 경우 체류 시간


@dataclass
class DetectDistressPayload:
    """
    조난 신호(SART, EPIRB) 감지.

    필수: 신호 위치 + 신호 타입
    선택: 신호 강도, 원인 정보
    """

    # ─ 필수 필드
    platform_id: str
    platform_name: str
    distress_type: str  # "sart" | "epirb" | "mayday" | "pan"
    latitude: float
    longitude: float
    timestamp: datetime

    # ─ 선택 필드
    signal_strength: Optional[float] = None
    frequency: Optional[str] = None  # 신호 주파수
    details: Optional[str] = None  # 추가 정보


@dataclass
class AnalyzeAnomalyPayload:
    """
    비정상 분석 (원인 파악).

    입력: DetectAnomalyPayload
    출력: 분석 결과 + 권고사항
    """

    # ─ 필수 필드
    alert_id: str
    platform_id: str
    original_anomaly_type: str
    analysis_result: str  # AI 분석 결과
    recommendation: Optional[str]
    confidence: float  # 0.0 ~ 1.0
    timestamp: datetime

    # ─ 메타
    ai_model: str  # "claude-haiku", "qwen2.5", ...
    execution_time_ms: float


@dataclass
class AnalyzeReportPayload:
    """
    Alert 기반 보고서 생성.

    입력: Alert ID 목록
    출력: 자동 생성 보고서
    """

    # ─ 필수 필드
    alert_ids: list[str]
    report_type: str  # "summary" | "detailed" | "incident"
    report_content: str
    timestamp: datetime

    # ─ 메타
    generation_time_ms: float


@dataclass
class LearnFeedbackPayload:
    """
    사용자 피드백 (경보 정확도 개선).

    입력: 사용자가 "이건 오탐지야" 또는 "이건 정확해" 표시
    처리: 거짓 경보율 계산 → 규칙 조정
    """

    # ─ 필수 필드
    alert_id: str
    feedback: str  # "false_positive" | "confirmed" | "partial"
    reason: Optional[str]
    timestamp: datetime
    user_id: Optional[str]

    # ─ 메타
    severity: str
    alert_type: str


@dataclass
class LearnRuleUpdatePayload:
    """
    Learning Agent가 발행한 규칙 조정 명령.

    입력: 거짓 경보 패턴
    출력: 새로운 threshold, 규칙 등
    """

    # ─ 필수 필드
    target_agent_id: str
    old_config: dict
    new_config: dict
    reason: str  # "FP rate 45%, reducing threshold..."
    timestamp: datetime
    confidence: float  # 이 조정이 유효한 확률


@dataclass
class SystemHeartbeatPayload:
    """
    Agent 상태 신호.

    주기적으로 발행하여 Supervisor가 모니터링.
    """

    # ─ 필수 필드
    agent_id: str
    status: str  # "healthy" | "degraded" | "error"
    timestamp: datetime

    # ─ 메타
    pending_tasks: int
    last_event_processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
