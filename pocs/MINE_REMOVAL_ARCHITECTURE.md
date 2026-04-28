# 기뢰 제거 시나리오 아키텍처

## 시스템 개요

CoWater POC 시스템에서 기뢰 제거 작업을 위한 완전한 아키텍처 구현:
- **실시간 장치 모니터링**: Moth meb 채널 기반 heartbeat
- **계층적 명령 전달**: Supervisor → Control Ship → Lower Agents (A2A 통신)
- **연결성 제약**: ROV 유선, AUV 수중음향 조건부 연결

---

## 1. 장치 계층 구조

### 계층 정의
```
계층 0: Supervisor (POC 05)
        ↓ A2A 명령 (JSON-RPC)
계층 1: Middle Agents (POC 04-05)
        - Control Ship (POC 04): USV/AUV/ROV 제어
        ↓ Moth 메시지 (real-time stream)
계층 2: Lower Agents (POC 01-03)
        - USV-01 (POC 01): 수표 탐색
        - AUV-01 (POC 02): 수심 측량, 음향 신호
        - ROV-01 (POC 03): 기뢰 제거 (유선 통신)
```

### 기뢰 제거 작업 역할 분담

| 장치 | POC | 역할 | 연결 방식 | 주요 기능 |
|------|-----|------|---------|---------|
| Supervisor | 05 | 작업 계획 & 감독 | A2A → Control Ship | 명령 발급, 진행 상황 모니터링 |
| Control Ship | 04 | 명령 해석 & 분배 | A2A ← Supervisor | 명령 변환, 다중 장치 제어 |
|              |    |                 | Moth → Lower Agents | 실시간 제어 신호 |
| USV | 01 | 지표 탐색 | Moth ← Control Ship | 소나 스캔, 위치 기록 |
| AUV | 02 | 수중 측량 | 음향통신 (조건부) | 수심 측정, 음성 신호 |
| ROV | 03 | 기뢰 제거 | 유선 (강제) | 영상 송신, 팔 제어 |

---

## 2. Heartbeat 모니터링 시스템

### 실시간 상태 추적

**Moth meb 채널 (broadcast stream)**:
```
device.heartbeat (meb type)
  ├─ device.heartbeat 발행자 #1 (USV): 1초 주기
  ├─ device.heartbeat 발행자 #2 (AUV): 1초 주기
  └─ device.heartbeat 발행자 #3 (ROV): 1초 주기
```

**Device Registration Server의 역할**:
```python
# 모든 장치의 heartbeat을 단일 meb 채널에서 수신
MothHeartbeatSubscriber
    ↓ 1초마다 각 장치에서 heartbeat 수신
    ↓ heartbeat_monitor.record_heartbeat() 호출
    ↓ 3초 이상 heartbeat 없으면 offline 표시
HeartbeatMonitor
    └─ Device 상태 업데이트: online → offline
```

### Heartbeat 페이로드

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

### 타임아웃 감지 로직

```python
# Device Registration Server
timeout_threshold = utcnow() - 3초

for device in devices:
    last_seen = device.agent.last_seen_at
    if last_seen < timeout_threshold:
        # 3초 이상 heartbeat 없음 = offline
        device.connected = False
        device.updated_at = now
        
        # 기뢰 제거 중 장치 오프라인 감지
        if device.device_type == "ROV" and job.status == "removing":
            job.emergency_stop()  # 즉시 중단
```

---

## 3. ROV 유선 연결 (강제 구조)

### ROV의 특성
- **반드시 유선으로 연결** → **어떤 middle layer 에이전트든** 통해서만 통신
- **실시간 영상** → 케이블로 전송
- **정밀 제어** → 레이턴시 최소화

### 유선 연결 설정

**등록 단계** (예: Control Ship에 연결):
```bash
POST /devices (ROV-01)
{
  "name": "ROV-01",
  "device_type": "ROV",
  "layer": "lower",
  "parent_id": 1,  # Middle layer: Control Ship (device_id=1)
  "connectivity": "wired",
  "tracks": [
    {"type": "VIDEO", "name": "main_camera"},
    {"type": "CONTROL", "name": "arm_control"}
  ]
}
```

**강제 라우팅 설정**:
```bash
# Control Ship에 연결
PATCH /devices/3/connectivity-state
{
  "parent_id": 1,           # Control Ship (POC 04)
  "force_parent_routing": true
}

응답:
{
  "id": 3,
  "device_type": "ROV",
  "parent_id": 1,
  "force_parent_routing": true,  # ← 유선 강제
  "connected": true
}
```

### ROV Parent 동적 변경

**다른 middle layer로 재할당** (예: Control USV로 변경):
```bash
PATCH /devices/3/connectivity-state
{
  "parent_id": 4,           # Control USV (POC XX)로 변경
  "force_parent_routing": true
}

응답:
{
  "id": 3,
  "device_type": "ROV",
  "parent_id": 4,  # ← parent 변경됨
  "force_parent_routing": true,
  "connected": true
}
```

**지원되는 Parent 목록**:
| Parent | device_id | POC | 역할 |
|--------|-----------|-----|------|
| USV Middle Layer | 2 | POC 04 | 수표 기반 제어 |
| Control Ship | 3 | POC 05 | 선박 기반 제어 |
| 기타 Middle Layer | N | POC XX | 필요 시 확장 가능 |

### 유선 라우팅 구현

**Control Ship의 ROV 제어**:
```python
# POC 04 (Control Ship)
async def handle_rov_command(command):
    if device.device_type == "ROV":
        # ROV는 항상 parent(Control Ship) 통한 통신
        assert device.force_parent_routing == True
        assert device.parent_id == 1
        
        # 케이블을 통한 직접 제어
        await rov_control_channel.send(command)
        
        # 영상 수신 (실시간)
        video_stream = await rov_control_channel.recv_video()
```

---

## 4. AUV 조건부 연결 (수중음향 통신)

### AUV의 특성
- **수면**: 직접 연결 (Wi-Fi, LTE)
- **수중**: 음향통신 (Control Ship을 통한 릴레이)

### 상태 변환 시퀀스

**시나리오: 기뢰 탐색 위해 AUV 투입**

```
[1] AUV 수면 상태 (surface)
    - parent_id: null (직접 연결)
    - 위치: 37.21°N, 126.97°E (수표 인근)

[2] Supervisor가 Control Ship에 AUV 잠수 명령
    POST /agents/{token}/message:send
    → action: "deploy_auv"
    → depth_target: 100m

[3] Control Ship이 Device Registry 업데이트
    PATCH /devices/2/auv-submersion
    { "is_submerged": true }
    
    응답:
    {
      "is_submerged": true,
      "submerged_at": "2026-04-28T14:35:00Z"
    }

[4] AUV가 수중으로 (음향통신 연결)
    PATCH /devices/2/connectivity-state
    { "parent_id": 1 }  # Control Ship과 음향 연결
    
    응답:
    {
      "parent_id": 1,
      "is_submerged": true,
      "connectivity": "acoustic"
    }

[5] Control Ship이 음향통신으로 AUV 제어
    - 깊이 조절: depth_adjustment
    - 스캔 범위: heading_adjustment
    - 센서 데이터: depth, pressure, sonar

[6] AUV가 수면 상태로 귀환
    PATCH /devices/2/auv-submersion
    { "is_submerged": false }
    
    응답:
    {
      "is_submerged": false,
      "surfaced_at": "2026-04-28T14:55:00Z",
      "parent_id": null  # 자동으로 direct 연결
    }
```

### 수중 통신 시뮬레이션 (선택사항)

```python
# 가짜 수중음향통신 채널 (fake underwater acoustic)
async def send_acoustic_message(device_id, message):
    """수중음향통신 지연 시뮬레이션"""
    device = registry.get_device(device_id)
    
    if device.device_type == "AUV" and device.is_submerged:
        # 수중: 음향 신호 전파 지연 (음속 ~1500m/s)
        await asyncio.sleep(0.5)  # 500ms 지연
        
        # 수심에 따른 신호 손실 시뮬레이션
        if device.depth > 500:
            if random() < 0.1:  # 10% 손실
                raise TimeoutError("Acoustic signal lost")
    else:
        # 수면: 일반 무선 통신
        await asyncio.sleep(0.05)  # 50ms 지연
```

---

## 5. A2A (Agent-to-Agent) 명령 흐름

### 기뢰 제거 작업 명령

**시작: Supervisor → Control Ship**

```bash
# POC 05 (Supervisor)
POST http://control-ship:9010/agents/{control_token}/message:send
{
  "message": {
    "role": "user",
    "parts": [{
      "type": "data",
      "data": {
        "message_type": "task.assign",
        "action": "execute_mine_removal",
        "mine_id": "MINE-001",
        "location": {
          "lat": 37.21,
          "lon": 126.97,
          "depth_m": 50
        },
        "sequence": [
          {
            "step": 1,
            "device": "USV-01",
            "action": "deploy",
            "sonar_params": {"frequency": "40kHz"}
          },
          {
            "step": 2,
            "device": "AUV-01",
            "action": "survey_depth",
            "target_depth": 50
          },
          {
            "step": 3,
            "device": "ROV-01",
            "action": "deploy",
            "tool": "cutting_arm",
            "video_required": true
          }
        ]
      }
    }]
  },
  "taskId": "MINE-REMOVAL-001"
}
```

**Control Ship이 명령 분해 및 실행**

```python
# POC 04 (Control Ship)
async def execute_mine_removal(task):
    # Step 1: USV 배치
    await self.command_device(
        device_id=1,
        channel="control.instruction.usv",
        payload={"action": "deploy_sonar", ...}
    )
    
    # Step 2: AUV 잠수 및 측량
    await self.command_device(
        device_id=2,
        action="auv_submersion",
        is_submerged=True
    )
    await self.command_device(
        device_id=2,
        channel="acoustic.control.auv",  # 음향통신
        payload={"action": "survey", ...}
    )
    
    # Step 3: ROV 배치 및 제거
    await self.command_device(
        device_id=3,
        channel="cable.control.rov",  # 유선 통신
        payload={"action": "deploy_arm", ...}
    )
    
    # 작업 진행 상황 모니터링
    while task.status != "completed":
        # Heartbeat 모니터링으로 장치 상태 확인
        for device_id in [1, 2, 3]:
            device = registry.get_device(device_id)
            if not device.connected:
                # 장치 오프라인 감지 → 즉시 중단
                await self.emergency_stop(task)
```

### 응답 흐름

**Lower Agent → Control Ship → Supervisor**

```python
# POC 01 (USV)
@app.post("/message:send")
async def message_send(request: A2ASendRequest):
    # 소나 스캔 완료
    result = {"sonar_data": [...]}
    
    # Control Ship에게 A2A로 응답
    return {
        "status": "completed",
        "result": result
    }

# POC 04 (Control Ship)이 수신하고 Supervisor에게 보고
POST http://supervisor:9010/agents/{supervisor_token}/message:send
{
  "message": {
    "role": "user",
    "parts": [{
      "type": "data",
      "data": {
        "message_type": "task.report",
        "task_id": "MINE-REMOVAL-001",
        "step": 1,
        "status": "completed",
        "sonar_data": [...]
      }
    }]
  }
}
```

---

## 6. 실시간 모니터링 대시보드

### Device Registration Server가 추적하는 정보

```
GET /devices
[
  {
    "id": 1,
    "name": "USV-01",
    "device_type": "USV",
    "layer": "lower",
    "connected": true,           # ← heartbeat으로 실시간 추적
    "last_seen_at": "2026-04-28T14:30:00Z",
    "latitude": 37.21,
    "longitude": 126.97,
    "heartbeat_topic": "device.heartbeat.1"
  },
  {
    "id": 2,
    "name": "AUV-01",
    "device_type": "AUV",
    "is_submerged": true,        # ← 수중 상태
    "submerged_at": "2026-04-28T14:35:00Z",
    "parent_id": 1,              # ← Control Ship 음향 연결
    "connected": true,
    "depth_m": 50                # ← 센서 데이터
  },
  {
    "id": 3,
    "name": "ROV-01",
    "device_type": "ROV",
    "force_parent_routing": true, # ← 유선 강제
    "parent_id": 1,
    "connected": true,
    "battery_percent": 92.3,     # ← 실시간 전력
    "heartbeat_topic": "device.heartbeat.3"
  }
]
```

### 기뢰 제거 진행 상황 시각화

```
작업: MINE-REMOVAL-001
상태: 진행 중
└─ [1] USV-01 소나 스캔      [████████░░] 80%
   시작: 14:30:00 / 예상: 300초 / 경과: 240초
   연결: ✅ online (heartbeat: 14:31:20)
   
└─ [2] AUV-01 수심 측량      [██░░░░░░░░] 20%
   상태: 수중 (깊이: 50m) / 음향통신 활성화
   연결: ✅ online (heartbeat: 14:31:21)
   위치: 37.210°N, 126.970°E
   
└─ [3] ROV-01 기뢰 제거      [░░░░░░░░░░] 0%
   상태: 배치 준비
   연결: ✅ online (heartbeat: 14:31:19)
   영상: ✅ 송신 중 (유선 케이블)
   배터리: 92.3%

⚠️ 경고 없음 | ✅ 모든 장치 정상
```

---

## 7. 장애 시나리오 처리

### 시나리오 1: ROV 통신 끊김 (유선)

```
[정상 상태]
ROV → 케이블 → Control Ship → Supervisor

[장애 발생]
15:30:00 - ROV heartbeat 수신 중단
15:30:03 - Device Registry: ROV offline으로 표시

[대응]
Control Ship이 Supervisor에게 긴급 보고:
{
  "event": "device_offline",
  "device_id": 3,
  "device_name": "ROV-01",
  "duration_seconds": 3,
  "action_required": "abort_mine_removal"
}

Supervisor가 모든 작업 중단 명령:
POST /agents/{control_token}/message:send
{
  "action": "emergency_stop",
  "reason": "ROV communication lost"
}

Control Ship 처리:
1. 모든 ROV 명령 중단
2. USV: 소나 중지
3. AUV: 상승 명령 발급
4. 모든 장치: 대기 상태로 전환
```

### 시나리오 2: AUV 수중에서 통신 복구

```
[정상 상태]
AUV (수중, 깊이 50m) ←→ 음향통신 ←→ Control Ship

[장애 발생]
AUV가 수심 너무 깊어짐 → 음향신호 감쇠
15:35:00 - AUV heartbeat 손실 (음향통신 두절)

[대응]
Device Registry의 HeartbeatMonitor:
- 3초 timeout 후 AUV offline으로 표시
- Control Ship에 알림

Control Ship의 자동 대응:
1. AUV "긴급 상승" 신호 발급
2. 상승하면서 heartbeat 회복 대기
3. heartbeat 수신 → AUV online으로 복구
4. 상태 정상화 후 작업 재개

대안: 수동 개입
- Supervisor가 AUV 회수 명령
- 수중음향통신 복구 될 때까지 작업 일시 중지
```

### 시나리오 3: USV 배터리 부족

```
[모니터링]
GET /devices/1
{
  "battery_percent": 15.2,
  "time_remaining_minutes": 12
}

[예측 알림]
Supervisor에 경고:
{
  "alert_type": "low_battery",
  "device": "USV-01",
  "battery_percent": 15.2,
  "action_recommendation": "recall_for_charging"
}

[대응]
Supervisor 명령:
POST /agents/{control_token}/message:send
{
  "action": "recall_device",
  "device": "USV-01",
  "destination": "charging_dock"
}

Control Ship이 USV 귀환 명령 발급 →
USV가 자동 항해로 충전소 복귀
```

---

## 8. 배포 및 테스트 가이드

### 필요한 외부 서비스
- **Moth Server**: 실시간 데이터 스트림 (기본: wss://cobot.center:8287)
- **Device Registry Server**: POC 00 (모든 POC의 등록 & heartbeat 중앙화)

### 기뢰 제거 시나리오 테스트 순서

```bash
# 1. Device Registration Server 시작
cd pocs/00-device-registration-server
python -m src.device_registration_server --port 8286

# 2. Lower Agents 시작 (POC 01-03)
cd pocs/01-usv-lower-agent && python -m src.main --port 9010  # USV
cd pocs/02-auv-lower-agent && python -m src.main --port 9011  # AUV (별도 포트)
cd pocs/03-rov-lower-agent && python -m src.main --port 9012  # ROV (별도 포트)

# 3. Middle Agent 시작 (POC 04)
cd pocs/04-usv-middle-agent && python -m src.main --port 9013  # Control Ship

# 4. Supervisor 시작 (POC 05)
cd pocs/05-control-ship-middle-agent && python -m src.main --port 9014  # Supervisor

# 5. 기뢰 제거 시나리오 실행
curl -X POST http://localhost:9014/agents/{supervisor_token}/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{
        "type": "data",
        "data": {
          "message_type": "task.assign",
          "action": "execute_mine_removal",
          ...
        }
      }]
    }
  }'
```

---

## 9. 핵심 기능 체크리스트

- ✅ Moth meb 기반 heartbeat 모니터링 (3초 timeout)
- ✅ ROV 유선 연결 강제 (parent routing)
- ✅ AUV 수중/수면 조건부 연결 (acoustic communication)
- ✅ A2A 계층적 명령 전달 (Supervisor → Control → Lower)
- ✅ 실시간 장치 상태 추적 (online/offline)
- ✅ 긴급 상황 대응 (device offline detection)
- ✅ 센서 데이터 통합 (GPS, DEPTH, BATTERY 등)

---

## 10. 향후 확장 사항

### Phase 2
- [ ] 자동 경로 계획 (AUV 경로 최적화)
- [ ] 영상 스트림 통합 (ROV 카메라 대시보드)
- [ ] 실시간 위치 지도 표시

### Phase 3
- [ ] 머신러닝 기반 기뢰 탐지 (수심/음향 데이터)
- [ ] 다중 기뢰 동시 처리
- [ ] 날씨/해류 고려 경로 계획

### Phase 4
- [ ] 실제 센서 통합 (LiDAR, 멀티빔 소나)
- [ ] 수중 네트워크 지연 시뮬레이션
- [ ] 분산 데이터 처리 (엣지 컴퓨팅)
