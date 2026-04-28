# CoWater 기뢰 제거 시나리오 완전 가이드

**최종 구현 상태**: 핵심 라우팅/등록/시나리오 스모크 검증 완료 ✅
**작성일**: 2026-04-29

---

## 📋 목차

1. [시스템 개요](#시스템-개요)
2. [핵심 기능](#핵심-기능)
3. [아키텍처](#아키텍처)
4. [ROV 유연한 설정](#rov-유연한-설정)
5. [기뢰 제거 시나리오](#기뢰-제거-시나리오)
6. [배포 및 테스트](#배포-및-테스트)

---

## 시스템 개요

CoWater POC 시스템은 기뢰 제거 작업을 위한 완전한 아키텍처를 구현합니다:

| 구성요소           | 기능                                           | 상태    |
| ------------------ | ---------------------------------------------- | ------- |
| **Moth Heartbeat** | 실시간 장치 모니터링                           | ✅ 완성 |
| **ROV 유선 연결**  | 케이블을 통한 강제 유선 통신                   | ✅ 완성 |
| **AUV 음향통신**   | 수중/수면 조건부 연결                          | ✅ 완성 |
| **A2A 통신**       | 계층적 명령 전달 (Supervisor → Middle → Lower) | ✅ 완성 |

---

## 핵심 기능

### 1. Moth Heartbeat 실시간 모니터링

**기능**: 모든 POC 장치의 건강 상태를 1초 주기로 추적하고, 3초 이상 heartbeat이 없으면 오프라인으로 표시.

**구현**:

- `MothHeartbeatSubscriber`: Moth meb 채널에서 모든 heartbeat 수신
- `HeartbeatMonitor`: 3초 timeout으로 online/offline 상태 감지
- **중요**: 상태 변경 시에만 DB에 반영 (매번이 아님)

**Heartbeat 페이로드**:

```json
{
  "device_id": 1,
  "agent_id": "01-usv-lower-agent",
  "layer": "lower",
  "timestamp": "2026-04-28T14:30:00Z",
  "status": "online",
  "battery_percent": 85.5
}
```

---

### 2. ROV 유선 연결 강제 (임의 Middle Layer)

**특징**: ROV는 항상 케이블로 연결되므로 **어떤 middle layer 에이전트든** 통해서만 통신 가능.

**Middle Layer 옵션**:
| Parent | POC | 역할 |
|--------|-----|------|
| **USV Middle Layer** | POC 04 | 수표 기반 제어 |
| **Control Ship** | POC 05 | 선박 기반 제어 |

**API - Control Ship 설정**:

```bash
PATCH /devices/3/connectivity-state
{
  "parent_id": 3,           # Control Ship (POC 05)
  "force_parent_routing": true
}

응답:
{
  "id": 3,
  "device_type": "ROV",
  "parent_id": 3,
  "force_parent_routing": true,  # 유선 강제
  "connected": true
}
```

**API - USV로 재할당**:

```bash
PATCH /devices/3/connectivity-state
{
  "parent_id": 2,           # USV Middle Layer (POC 04)
  "force_parent_routing": true
}
```

**동적 변경**: 작업 중에도 parent를 재할당할 수 있음.

---

### 3. AUV 수중음향통신 (조건부 연결)

**특징**: AUV는 **수중일 때만** middle layer와 음향통신, **수면일 때는** 직접 연결.

**상태 변환 시나리오**:

#### 수면 → 잠수

```bash
# 1단계: AUV 잠수
PATCH /devices/2/auv-submersion
{
  "is_submerged": true
}

# 2단계: 음향통신 연결
PATCH /devices/2/connectivity-state
{
  "parent_id": 1,           # Middle layer와 음향 연결
  "force_parent_routing": false
}

응답:
{
  "is_submerged": true,
  "parent_id": 1,           # 중간 계층과 연결
  "connectivity": "acoustic"
}
```

#### 잠수 → 수면

```bash
PATCH /devices/2/auv-submersion
{
  "is_submerged": false
}

응답:
{
  "is_submerged": false,
  "parent_id": null,        # 자동으로 직접 연결
  "surfaced_at": "2026-04-28T14:40:00Z"
}
```

---

### 4. A2A (Agent-to-Agent) 통신

**모든 POC 통합**: POC 01-06 모두 `pocs/shared/a2a.py` 및 `pocs/shared/command.py` 사용.

**메시지 구조**:

```python
A2AMessage(
  role="user",
  parts=[
    A2APart(
      type="data",
      data={
        "message_type": "task.assign",
        "action": "deploy_rov",
        "params": {...}
      }
    )
  ]
)
```

**계층적 흐름**:

```
Supervisor (POC 06)
    ↓ A2A /message:send
Middle Layer (POC 04-05)
    ↓ Moth 메시지 발행
Lower Agents (POC 01-03)
    ↓ 작업 수행
```

---

## 아키텍처

### 계층 구조

```
POC 06 - System Supervisor
    ↓ A2A 명령 (JSON-RPC)
POC 04-05 - Middle Layer (USV, Control Ship)
    ├─ Moth 제어 ↓
    │
    ├─ POC 01 - USV Lower (Direct WiFi)
    ├─ POC 02 - AUV (Acoustic when submerged)
    └─ POC 03 - ROV (Wired - always through parent)

POC 00 - Device Registry Server (Heartbeat 모니터링)
```

### Heartbeat 모니터링 흐름

```
POC 01-03 (1초마다)
    ↓ heartbeat 발행
device.heartbeat meb (Moth broadcast)
    ↓
MothHeartbeatSubscriber (POC 00)
    ↓ heartbeat_monitor.record_heartbeat()
HeartbeatMonitor (3초 timeout)
    ↓ 상태 변경 시만 반영
DeviceRegistry
```

---

## ROV 유연한 설정

### 상황별 Parent 선택

**시나리오 1: 해안 근처 (얕은 수심)**

```bash
# USV에서 직접 ROV 제어
PATCH /devices/3/connectivity-state
{
  "parent_id": 2,  # USV Middle Layer
  "force_parent_routing": true
}

명령 흐름:
Supervisor → USV → ROV (기뢰 제거)
```

**시나리오 2: 원해 (깊은 수심)**

```bash
# Control Ship에서 원거리 ROV 제어
PATCH /devices/3/connectivity-state
{
  "parent_id": 3,  # Control Ship
  "force_parent_routing": true
}

명령 흐름:
Supervisor → Control Ship → ROV (기뢰 제거)
```

**시나리오 3: 작업 중 전환**

```bash
# 초기: USV 제어
PATCH /devices/3/connectivity-state { "parent_id": 2 }

# 중간: 선박 접근 후 Control Ship으로 전환
PATCH /devices/3/connectivity-state { "parent_id": 3 }

# 최종: 회수 시 다시 USV로
PATCH /devices/3/connectivity-state { "parent_id": 2 }
```

---

## 기뢰 제거 시나리오

### 전체 작업 흐름

**Step 1: Supervisor가 기뢰 제거 임무 발령**

```bash
POST /message:send
{
  "message": {
    "role": "user",
    "parts": [{
      "type": "data",
      "data": {
        "message_type": "task.assign",
        "action": "execute_mine_removal",
        "mine_id": "MINE-001",
        "location": {"lat": 37.21, "lon": 126.97, "depth_m": 50},
        "sequence": [
          {"step": 1, "device": "USV-01", "action": "deploy"},
          {"step": 2, "device": "AUV-01", "action": "survey_depth"},
          {"step": 3, "device": "ROV-01", "action": "remove_mine"}
        ]
      }
    }]
  },
  "taskId": "MINE-REMOVAL-001"
}
```

**Step 2: Control Ship이 명령 분해**

```python
# Step 1: USV 배치
→ Moth: control.instruction.usv

# Step 2: AUV 잠수 및 측량
→ PATCH /devices/2/auv-submersion { "is_submerged": true }
→ PATCH /devices/2/connectivity-state { "parent_id": 1 }
→ Moth: acoustic.control.auv

# Step 3: ROV 배치 및 제거
→ PATCH /devices/3/connectivity-state { "parent_id": 3 }
→ Moth: cable.control.rov
```

**Step 3: 장치 오프라인 감지 시**

```
기뢰 제거 중 ROV heartbeat 끊김 감지
    ↓ 3초 이상 no heartbeat
Device Registry: ROV offline으로 표시
    ↓
Control Ship에 긴급 알림
    ↓
Supervisor에 보고
    ↓
모든 작업 중단 (Emergency Stop)
```

---

## 배포 및 테스트

### 필수 구성요소

```bash
# 1. Device Registration Server 시작
cd pocs/00-device-registration-server
python device_registration_server.py --port 9100

# 2. Lower Agents 시작
python pocs/01-usv-lower-agent/device_agent.py --port 9111
python pocs/02-auv-lower-agent/device_agent.py --port 9112
python pocs/03-rov-lower-agent/device_agent.py --port 9113

# 3. Middle Layer 시작
python pocs/04-usv-middle-agent/device_agent.py --port 9114
python pocs/05-control-ship-middle-agent/device_agent.py --port 9115

# 4. Supervisor 시작
python pocs/06-system-supervisor-agent/system_agent.py --port 9116
```

### 시나리오 스모크 테스트

외부 Moth/Ollama 서버 없이 레지스트리 라우팅과 기뢰제거 절차를 검증하려면:

```bash
python pocs/docs/run_mine_removal_scenario.py --format timeline
```

성공 시 다음 조건이 모두 `OK`로 출력됩니다:

```text
OK auv_submerged_via_parent
OK rov_wired_force_parent
OK unique_track_endpoints
```

### 테스트 체크리스트

- [ ] **Heartbeat 모니터링**: POC 하나를 중단했을 때 3초 후 offline으로 표시되는지 확인
- [ ] **ROV 유선 설정**: `PATCH /devices/3/connectivity-state`로 parent 변경 가능한지 확인
- [ ] **AUV 잠수**: `PATCH /devices/2/auv-submersion`로 수중/수면 전환 가능한지 확인
- [ ] **A2A 통신**: Supervisor에서 Lower Agent로 명령이 전달되는지 확인
- [ ] **기뢰 제거 시나리오**: 전체 작업 흐름이 정상 작동하는지 확인

### 테스트 예시

```bash
# Heartbeat 모니터링 테스트
curl http://localhost:9100/devices
# → 모든 디바이스가 connected=true인지 확인

# ROV parent 변경 테스트
curl -X PATCH http://localhost:9100/devices/3/connectivity-state \
  -H "Content-Type: application/json" \
  -d '{"parent_id": 2, "force_parent_routing": true}'

# AUV 잠수 테스트
curl -X PATCH http://localhost:9100/devices/2/auv-submersion \
  -H "Content-Type: application/json" \
  -d '{"is_submerged": true}'
```

---

## 핵심 요약

✅ **검증된 기능**:

- Moth heartbeat 실시간 모니터링 (3초 timeout)
- ROV 유선 연결 강제 (임의 middle layer 선택 가능)
- AUV 수중음향 조건부 연결
- A2A 계층적 통신 (POC 01-06)
- 기뢰 제거 시나리오 아키텍처

✅ **구현 파일**:

- `pocs/00-device-registration-server/src/transport/moth_subscriber.py`
- `pocs/00-device-registration-server/src/registry/device_registry.py`
- `pocs/shared/a2a.py`, `pocs/shared/command.py`
- POC 01-06의 모든 controller/api.py

✅ **배포 준비 상태**: 로컬 스모크 테스트 가능. 실제 Moth/Ollama/장시간 WebSocket 운영 검증은 별도 필요.

---

**마지막 업데이트**: 2026-04-29
