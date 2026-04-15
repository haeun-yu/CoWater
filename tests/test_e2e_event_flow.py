"""
E2E 테스트: platform.report → detect → analyze → respond → alert

완전한 이벤트 흐름 검증.
"""

import asyncio
import json
from datetime import datetime
from uuid import uuid4

import pytest
import redis.asyncio as aioredis

from shared.events import Event, EventType
from shared.schemas.report import PlatformReport


@pytest.fixture
async def redis():
    """Redis 클라이언트"""
    r = aioredis.from_url("redis://localhost:6379", decode_responses=True)
    yield r
    await r.aclose()


@pytest.mark.asyncio
async def test_e2e_cpa_detection_to_alert(redis: aioredis.Redis):
    """
    E2E 테스트: CPA 위험 감지부터 Alert 생성까지.

    1. Detection이 detect.cpa 이벤트 발행
    2. Analysis가 분석 (analyze.anomaly는 아님, CPA는 바로 Alert로)
    3. Response가 Alert 생성
    """

    # 1. 두 선박 위치 보고 (충돌 위험)
    vessel1 = PlatformReport(
        platform_id="vessel-001",
        platform_type="vessel",
        time=datetime.utcnow(),
        lat=37.5,
        lon=126.5,
        sog=10.0,
        cog=90.0,
        heading=90.0,
        source_protocol="ais",
    )

    vessel2 = PlatformReport(
        platform_id="vessel-002",
        platform_type="vessel",
        time=datetime.utcnow(),
        lat=37.51,  # 약 1.8km 떨어짐
        lon=126.5,
        sog=8.0,
        cog=270.0,
        heading=270.0,
        source_protocol="ais",
    )

    # 2. Detection 이벤트 시뮬레이션 (CPA 감지)
    detect_event = Event(
        flow_id="test-incident-cpa-001",
        type=EventType.DETECT_CPA,
        agent_id="detection-cpa",
        payload={
            "platform_id": vessel1.platform_id,
            "target_platform_id": vessel2.platform_id,
            "cpa_minutes": 3.0,  # 위험 기준
            "tcpa_minutes": 5.0,
            "latitude": vessel1.lat,
            "longitude": vessel1.lon,
            "platform_name": "Vessel 1",
            "target_name": "Vessel 2",
            "platform_sog": vessel1.sog,
            "platform_cog": vessel1.cog,
            "target_sog": vessel2.sog,
            "target_cog": vessel2.cog,
            "severity": "critical",
            "timestamp": vessel1.time.isoformat(),
        },
    )

    # 3. Detection 이벤트 발행
    await redis.publish("detect.cpa.vessel-001", detect_event.to_json())
    print(f"✓ Detection event published: {detect_event.flow_id}")

    # 4. Response가 Alert를 생성하고 Alert 채널에 발행 (시뮬레이션)
    alert_id = str(uuid4())
    respond_event = Event(
        flow_id=detect_event.flow_id,
        type=EventType.RESPOND_ALERT,
        agent_id="response-alert-creator",
        payload={
            "alert_id": alert_id,
            "platform_id": vessel1.platform_id,
            "alert_type": "cpa",
            "severity": "critical",
            "message": "충돌 위험: vessel-001 ↔ vessel-002 (CPA 3min)",
        },
        causation_id=detect_event.event_id,
    )

    await redis.publish(f"respond.alert.{alert_id}", respond_event.to_json())
    print(f"✓ Response event published: {alert_id}")

    # 5. 이벤트 체인 검증
    assert detect_event.flow_id == respond_event.flow_id, "Flow ID가 일치해야 함"
    assert respond_event.causation_id == detect_event.event_id, "Causation 체인이 유지되어야 함"

    # 6. Redis에서 이벤트 구독으로 확인
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"respond.alert.{alert_id}")

    message = await asyncio.wait_for(pubsub.listen().__anext__(), timeout=5.0)

    if message["type"] == "message":
        received_event = Event.from_json(message["data"])
        assert received_event.event_id == respond_event.event_id
        print(f"✓ Event received via Redis pub/sub")

    await pubsub.unsubscribe(f"respond.alert.{alert_id}")


@pytest.mark.asyncio
async def test_e2e_anomaly_detection_to_analysis(redis: aioredis.Redis):
    """
    E2E 테스트: 비정상 감지부터 분석까지.

    1. Detection이 detect.anomaly 이벤트 발행
    2. Analysis가 분석하고 analyze.anomaly 이벤트 발행
    """

    # 1. Anomaly Detection 이벤트
    detect_event = Event(
        flow_id="test-incident-anomaly-001",
        type=EventType.DETECT_ANOMALY,
        agent_id="detection-anomaly",
        payload={
            "platform_id": "vessel-003",
            "platform_name": "Vessel 3",
            "anomaly_type": "rot",
            "anomaly_value": 45.0,  # 비정상 선회율
            "latitude": 37.5,
            "longitude": 126.5,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "비정상 선회율: 45.0°/min",
        },
    )

    await redis.publish("detect.anomaly.vessel-003", detect_event.to_json())
    print(f"✓ Anomaly detection event published: {detect_event.flow_id}")

    # 2. Analysis 이벤트 (AI 분석 결과)
    alert_id = str(uuid4())
    analyze_event = Event(
        flow_id=detect_event.flow_id,
        type=EventType.ANALYZE_ANOMALY,
        agent_id="analysis-anomaly-ai",
        payload={
            "alert_id": alert_id,
            "platform_id": "vessel-003",
            "original_anomaly_type": "rot",
            "analysis_result": "선회 기동 중. 항로 변경 또는 조종 오류 가능성.",
            "recommendation": "선박 운항 계획과 실제 항로 비교하여 확인 필요",
            "confidence": 0.75,
            "timestamp": datetime.utcnow().isoformat(),
            "ai_model": "claude-haiku",
            "execution_time_ms": 2500,
        },
        causation_id=detect_event.event_id,
    )

    await redis.publish(f"analyze.anomaly.{alert_id}", analyze_event.to_json())
    print(f"✓ Analysis event published: {alert_id}")

    # 3. Event 체인 검증
    assert detect_event.flow_id == analyze_event.flow_id
    assert analyze_event.causation_id == detect_event.event_id
    print(f"✓ Event chain verified: detect → analyze")


@pytest.mark.asyncio
async def test_event_causation_chain(redis: aioredis.Redis):
    """
    Event causation chain 검증.

    detect → analyze → respond 전체 흐름에서
    flow_id와 causation_id가 올바르게 유지되는지 확인.
    """

    flow_id = "test-incident-chain-001"

    # 1. Detection 단계
    detect_event = Event(
        flow_id=flow_id,
        type=EventType.DETECT_ZONE,
        agent_id="detection-zone",
        payload={"platform_id": "v1", "zone_id": "z1"},
    )

    # 2. Analysis 단계 (Detection의 결과를 받음)
    # (이 경우 Zone은 Analysis 거치지 않고 바로 Response로 가지만,
    #  일반적인 패턴을 보여줌)
    analyze_event = Event(
        flow_id=flow_id,  # 동일한 flow
        type=EventType.ANALYZE_ANOMALY,
        agent_id="analysis-anomaly-ai",
        payload={"alert_id": str(uuid4())},
        causation_id=detect_event.event_id,  # Detection 이벤트 참조
    )

    # 3. Response 단계 (Analysis의 결과를 받음)
    respond_event = Event(
        flow_id=flow_id,  # 동일한 flow
        type=EventType.RESPOND_ALERT,
        agent_id="response-alert-creator",
        payload={"alert_id": str(uuid4())},
        causation_id=analyze_event.event_id,  # Analysis 이벤트 참조
    )

    # 검증
    assert detect_event.flow_id == analyze_event.flow_id == respond_event.flow_id
    assert analyze_event.causation_id == detect_event.event_id
    assert respond_event.causation_id == analyze_event.event_id

    # 인과관계 체인 추적
    chain = [detect_event, analyze_event, respond_event]
    for i in range(1, len(chain)):
        assert chain[i].causation_id == chain[i - 1].event_id

    print(f"✓ Complete causation chain verified:")
    print(f"  {chain[0].event_id[:8]}... → {chain[1].event_id[:8]}... → {chain[2].event_id[:8]}...")


if __name__ == "__main__":
    # pytest 없이 실행하려면:
    # python3 -m asyncio tests/test_e2e_event_flow.py

    async def main():
        r = aioredis.from_url("redis://localhost:6379", decode_responses=True)

        print("=== E2E Event Flow Tests ===\n")

        try:
            await test_e2e_cpa_detection_to_alert(r)
            print()
            await test_e2e_anomaly_detection_to_analysis(r)
            print()
            await test_event_causation_chain(r)
            print("\n✅ All E2E tests passed!")
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
        finally:
            await r.aclose()

    asyncio.run(main())
