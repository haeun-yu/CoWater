# PoC 11: A2A Inter-Agent Protocol

## Goal

Learning Agent가 Detection Agent에게 rule update 제안을 **Google A2A (Agent-to-Agent)** 표준으로 전송하는
표준 에이전트 간 통신 패턴을 검증합니다.

A2A는 Google이 주도하고 Anthropic이 파트너로 참여한 **공개 에이전트 상호운용성 표준** (2025년 4월 공개)입니다.

## Protocol Flow

```
[Learning Agent] — FP rate 높음 감지
        ↓
    1️⃣ Agent Card 조회
        GET /.well-known/agent.json
        → Detection Agent의 skill 확인: "suggest_rule_update"
        ↓
    2️⃣ Task 생성 및 전송
        POST /tasks/send
        {
          "skill_id": "suggest_rule_update",
          "message": {
            "role": "user",
            "parts": [{
              "type": "data",
              "data": {
                "target_agent_id": "detection-cpa",
                "new_config": {"critical_cpa_nm": 1.0},
                "confidence": 0.72  # >= 0.6 → 즉시 적용
              }
            }]
          }
        }
        ↓
[Detection Agent] — Task 처리
        ↓
    3️⃣ 신뢰도 판단 + 규칙 적용
        confidence >= 0.6:
          • 즉시 적용 (applied_changes)
          • 현재 설정에 반영
        
        confidence < 0.6:
          • 보류 처리 (pending_changes)
          • 관제사 수동 검토 필요
        ↓
    4️⃣ 결과 반환
        {
          "id": "task-uuid",
          "status": {"state": "completed"},
          "artifacts": [{
            "name": "rule_update_result",
            "parts": [{
              "type": "data",
              "data": {
                "target_agent_id": "detection-cpa",
                "applied_changes": {
                  "critical_cpa_nm": {"from": 0.5, "to": 1.0}
                },
                "pending_changes": {},
                "current_config": {...}
              }
            }]
          }]
        }
        ↓
[Learning Agent] — 결과 확인
        ↓
    5️⃣ artifacts 파싱
        • applied_changes 확인
        • pending_changes 확인 (추후 관제사 승인 필요)
        • 현재 설정 동기화
        ↓
    ✅ 양방향 피드백 루프 완성
```

## Technical Stack

### Standards
- **A2A**: Google A2A Protocol (2025-04)
- **Transport**: HTTP REST
- **Format**: JSON
- **Discovery**: Agent Card (`.well-known/agent.json`)

### Architecture
```
┌──────────────────────────────────────────────────────┐
│ learning-agent (A2A Client)                          │
│  ├─ Agent discovery (GET /.well-known/agent.json)  │
│  ├─ Task send (POST /tasks/send)                   │
│  └─ Result parsing (artifacts)                     │
└────────────────────┬─────────────────────────────────┘
                     │ (A2A Task JSON)
┌────────────────────▼─────────────────────────────────┐
│ detection-agent (A2A Server)                         │
│  ├─ Agent Card: skills, capabilities               │
│  ├─ Task executor: confidence-based decision       │
│  └─ Result artifacts: applied/pending changes      │
└──────────────────────────────────────────────────────┘
```

## Files

| 파일 | 역할 |
|------|------|
| `requirements.txt` | 의존성: fastapi, uvicorn, httpx, pydantic |
| `src/detection_agent_server.py` | A2A Server (Agent Card + Task processing) |
| `src/learning_agent_client.py` | A2A Client (Task send + result parsing) |
| `docker-compose.yml` | detection-agent + learning-agent 오케스트레이션 |

## Run

### Docker (권장)
```bash
cd pocs/11-a2a-interagent

# 방법 1: docker compose
docker compose up

# 방법 2: 배경에서 실행
docker compose up -d
docker compose logs -f learning-agent
```

### Local (Python 직접)
```bash
cd pocs/11-a2a-interagent

# Terminal 1: Detection Agent 서버 시작
pip install -r requirements.txt
python src/detection_agent_server.py
# 출력: "Starting server on 0.0.0.0:8001..."

# Terminal 2: Learning Agent 클라이언트 실행
export DETECTION_AGENT_URL=http://localhost:8001
python src/learning_agent_client.py
```

## Expected Output

```
══════════════════════════════════════════════════════════════════════════════
  CoWater A2A Inter-Agent Protocol POC — Learning ↔ Detection
══════════════════════════════════════════════════════════════════════════════

Detection Agent URL: http://detection-agent:8001
Protocol: Google A2A (2025-04)

[1] Discovering Detection Agent: GET http://detection-agent:8001/.well-known/agent.json

✓ Agent Card Retrieved
  Name: cowater-detection-agent
  Display Name: CoWater Detection Agent
  Version: 1.0.0
  API Version: a2a-2025-04
  Capabilities: {"streaming": false, "pushNotifications": false, "rateLimit": null}

  Skills:
    - suggest_rule_update: Suggest Rule Update
      Learning Agent의 rule update 제안을 수신하고 처리합니다...

──────────────────────────────────────────────────────────────────────────────
  시나리오 1: CPA Rule 조정 (High Confidence)
──────────────────────────────────────────────────────────────────────────────

상황 분석:
  - Detection: CPA agent
  - 기간: 최근 24시간
  - 탐지: 45건, 오탐지(FP): 15건 (33.3%)
  - 원인: critical_cpa_nm = 0.5 NM이 너무 낮음
  - 처방: threshold 상향 (0.5 → 1.0 NM)
  - 신뢰도: 0.72 (높음) → 즉시 적용 가능

[2] Sending A2A Task: POST http://detection-agent:8001/tasks/send

✓ Task Sent and Processed
  Task ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Status: completed

[3] Querying Task: GET http://detection-agent:8001/tasks/a1b2c3d4-e5f6-7890-abcd-ef1234567890

✓ Task Status
  Task ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
  Status: completed

[4] 결과 분석

  ✓ 규칙 업데이트 결과:
    대상 Agent: detection-cpa
    신뢰도: 0.72
    처리 시각: 2026-04-22T10:35:12.345678+00:00

    ✅ 즉시 적용된 변경:
      • critical_cpa_nm: 0.5 → 1.0 (confidence 0.72)

    ⏸ 보류된 변경:

    📊 현재 설정 (업데이트됨):
      {
        "critical_cpa_nm": 1.0,
        "warning_cpa_nm": 2.0,
        "critical_tcpa_min": 10.0,
        "warning_tcpa_min": 20.0
      }

──────────────────────────────────────────────────────────────────────────────
  시나리오 2: Anomaly Rule 조정 (Low Confidence)
──────────────────────────────────────────────────────────────────────────────

상황 분석:
  - Detection: Anomaly agent
  - 파라미터: rot_threshold (Rate of Turn)
  - 현재값: 20°/min
  - 제안값: 30°/min (더 큰 회전만 이상으로 감지)
  - 신뢰도: 0.45 (낮음) → 즉시 적용 불가
  - 처리: pending 상태로 보류 (관제사 수동 승인 필요)

[2] Sending A2A Task: POST http://detection-agent:8001/tasks/send

✓ Task Sent and Processed
  Task ID: f1e2d3c4-b5a6-9870-dcba-4321fedcba98
  Status: completed

[3] Querying Task: GET http://detection-agent:8001/tasks/f1e2d3c4-b5a6-9870-dcba-4321fedcba98

✓ Task Status
  Task ID: f1e2d3c4-b5a6-9870-dcba-4321fedcba98
  Status: completed

[4] 결과 분석

  ⏸ 규칙 업데이트 결과:
    대상 Agent: detection-anomaly
    신뢰도: 0.45
    처리 시각: 2026-04-22T10:35:12.987654+00:00

    ✅ 즉시 적용된 변경: (없음)

    ⏸ 보류된 변경:
      • rot_threshold: 20.0 → 30.0
        사유: confidence < 0.6 (신뢰도 0.45 < 0.6)
        👉 관제사 수동 검토 필요

    📊 현재 설정:
      {
        "ais_timeout_sec": 90,
        "rot_threshold": 20.0,
        "heading_threshold": 45.0,
        "speed_drop_threshold": 5.0
      }

──────────────────────────────────────────────────────────────────────────────
  요약
──────────────────────────────────────────────────────────────────────────────

✅ A2A 통신 성공

A2A 워크플로우:
  1. Learning Agent가 Detection Agent의 Agent Card 조회
     → Capability discovery (지원하는 skill 확인)

  2. Learning Agent가 rule update Task 생성 + 전송
     POST /tasks/send → Task ID, status, payload 포함

  3. Detection Agent가 신뢰도 판단:
     confidence >= 0.6 → 즉시 적용 (applied_changes)
     confidence < 0.6  → 보류 처리 (pending_changes)

  4. Learning Agent가 artifacts에서 결과 확인
     GET /tasks/{task_id} 또는 POST 응답

이점:
  • 표준 A2A 프로토콜 사용 → 타사 에이전트와 상호운용 가능
  • JSON 기반 → 언어/플랫폼 독립적
  • Agent Card로 capability 사전 discovery
  • 신뢰도 기반 자동/수동 처리 분기
  • Artifacts로 상세한 처리 결과 반환

🎯 POC 목표 달성: Detection ↔ Learning 간 표준 A2A 통신 검증

══════════════════════════════════════════════════════════════════════════════
```

## Success Criteria

✅ **Functional**
- Agent Card endpoint (`GET /.well-known/agent.json`) 제공
- Task send endpoint (`POST /tasks/send`) 구현
- Task query endpoint (`GET /tasks/{task_id}`) 구현
- Confidence 기반 규칙 적용/보류 로직 작동

✅ **Standards Compliance**
- A2A 스펙 준수: Agent Card, Task, Artifacts
- JSON 기반 메시지 형식
- HTTP REST API

✅ **Production Readiness**
- Error handling: 잘못된 skill/agent 처리
- Task 상태 추적: working → completed | failed
- Artifacts로 상세 결과 반환
- Logging: 모든 step 추적 가능

## Included

- A2A Server (FastAPI + Pydantic)
  - Agent Card endpoint
  - Task send endpoint (동기 처리)
  - Task query endpoint
  - Confidence-based decision logic

- A2A Client (httpx)
  - Agent discovery
  - Task send + result parsing
  - 2개 시나리오 (high/low confidence)

- Docker 오케스트레이션
  - Service health check
  - Service dependency management

## Excluded

- Async task processing (동기만 구현)
- Persistent task storage (인메모리만)
- Authentication/Authorization
- Real Learning Agent 연동 (시뮬레이션만)

## Protocol Details

### A2A Agent Card

```json
{
  "name": "cowater-detection-agent",
  "displayName": "CoWater Detection Agent",
  "description": "...",
  "url": "http://detection-agent:8001",
  "version": "1.0.0",
  "apiVersion": "a2a-2025-04",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [
    {
      "id": "suggest_rule_update",
      "name": "Suggest Rule Update",
      "description": "...",
      "inputModes": ["data"],
      "outputModes": ["data"]
    }
  ]
}
```

### A2A Task Lifecycle

```
submitted  →  working  →  completed  ┐
                          ↓          │
                       artifacts     │
                       (results)     │
                                     ↓
                                   failed  →  error artifacts
```

### Confidence-based Logic

```python
if confidence >= 0.6:
    # 즉시 적용
    applied_changes[param] = {
        "from": old_value,
        "to": new_value,
        "confidence": confidence
    }
else:
    # 보류 처리 (관제사 수동 검토)
    pending_changes[param] = {
        "current": old_value,
        "proposed": new_value,
        "confidence": confidence,
        "reason": "confidence < 0.6"
    }
```

## Comparison: Redis vs A2A

| 관점 | Redis Pub/Sub (현재) | A2A HTTP (POC) |
|------|---------------------|----------------|
| 통신 | 이벤트 브로드캐스트 | 양방향 요청-응답 |
| 프로토콜 | Redis Protocol | HTTP REST |
| 표준화 | CoWater 커스텀 | Google A2A 공개 |
| 상호운용성 | CoWater 한정 | 타사 에이전트 호환 |
| 응답 확인 | 어려움 | Task query로 즉시 확인 |
| 신뢰도 처리 | 없음 | 자동/수동 분기 가능 |

## References

- [A2A Protocol (Google)](https://agent-to-agent.ai/) — 공개 표준
- [Anthropic A2A Support](https://docs.anthropic.com/) — Partner 참여
- [Learning Agent Rules](../../services/learning-agents/learning_agent.py)
- [Detection Agent Config](../../services/detection-agents/config.py)
