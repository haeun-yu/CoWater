# ROV 유연한 Parent 설정 가이드

## 개요

ROV(Remote Operated Vehicle)는 **유선 연결이 필수**이지만, parent(제어 센터)는 **임의로 설정**할 수 있습니다.

---

## Middle Layer 옵션

CoWater POC 시스템에는 여러 middle layer 에이전트가 있습니다:

| Parent | POC | 역할 | device_id |
|--------|-----|------|-----------|
| **USV Middle Layer** | POC 04 | 수표 기반 ROV 제어 | 2 |
| **Control Ship** | POC 05 | 선박 기반 ROV 제어 | 3 |
| 기타 Middle Layer | POC XX | 확장 가능 | N |

---

## ROV Parent 설정 (API)

### Option 1: USV (POC 04)에 연결

```bash
# USV Middle Layer를 ROV의 parent로 설정
PATCH http://device-registry:8286/devices/3/connectivity-state
{
  "parent_id": 2,
  "force_parent_routing": true
}

응답:
{
  "id": 3,
  "name": "ROV-01",
  "device_type": "ROV",
  "parent_id": 2,  # ← USV Middle Layer
  "force_parent_routing": true,
  "connected": true
}

이제 모든 ROV 명령이 USV를 통해 전달됨:
Supervisor → USV (POC 04) → ROV (POC 03)
```

### Option 2: Control Ship (POC 05)에 연결

```bash
# Control Ship을 ROV의 parent로 설정
PATCH http://device-registry:8286/devices/3/connectivity-state
{
  "parent_id": 3,
  "force_parent_routing": true
}

응답:
{
  "id": 3,
  "name": "ROV-01",
  "device_type": "ROV",
  "parent_id": 3,  # ← Control Ship
  "force_parent_routing": true,
  "connected": true
}

이제 모든 ROV 명령이 Control Ship을 통해 전달됨:
Supervisor → Control Ship (POC 05) → ROV (POC 03)
```

### Option 3: 동적으로 Parent 변경 (재할당)

```bash
# USV에서 Control Ship으로 전환
PATCH http://device-registry:8286/devices/3/connectivity-state
{
  "parent_id": 3,  # 새로운 parent로 변경
  "force_parent_routing": true
}

응답:
{
  "id": 3,
  "device_type": "ROV",
  "parent_id": 3,  # ← 변경됨
  "force_parent_routing": true,
  "connected": true
}

# 다시 USV로 전환
PATCH http://device-registry:8286/devices/3/connectivity-state
{
  "parent_id": 2,  # 다시 USV로 변경
  "force_parent_routing": true
}
```

---

## 기뢰 제거 시나리오에서의 활용

### 시나리오 1: 해안 근처 - USV 제어

```
[상황] 기뢰가 해안 근처(얕은 수심) 위치
[작업] 수표의 USV에서 직접 ROV 제어가 효율적

ROV Parent 설정: USV (POC 04)
PATCH /devices/3/connectivity-state
{
  "parent_id": 2,  # USV
  "force_parent_routing": true
}

명령 흐름:
Supervisor (POC 05)
  ↓ "deploy ROV" 명령
USV (POC 04) [parent]
  ↓ 유선 케이블로 제어
ROV (POC 03)
  ↓ 기뢰 제거 작업 수행
```

### 시나리오 2: 원해 - Control Ship 제어

```
[상황] 기뢰가 원해(깊은 수심) 위치
[작업] 선박의 Control Ship에서 원거리 ROV 제어가 필요

ROV Parent 설정: Control Ship (POC 05)
PATCH /devices/3/connectivity-state
{
  "parent_id": 3,  # Control Ship
  "force_parent_routing": true
}

명령 흐름:
Supervisor (POC 05) [= 선박의 Control Ship]
  ↓ "deploy ROV" 명령 (직접 발행)
Control Ship (POC 05) [parent]
  ↓ 유선 케이블로 제어
ROV (POC 03)
  ↓ 기뢰 제거 작업 수행
```

### 시나리오 3: 중간 전환

```
[작업 진행]
1. 초기: USV에서 ROV 배치
   PATCH /devices/3/connectivity-state { "parent_id": 2 }

2. 중간 전환: 선박 접근 후 Control Ship으로 재할당
   PATCH /devices/3/connectivity-state { "parent_id": 3 }

3. 최종: 작업 완료 후 회수
   PATCH /devices/3/connectivity-state { "parent_id": 2 }

모든 전환이 실시간으로 가능 (ROV 작동 중에도)
```

---

## 핵심 특징

✅ **유연성**: ROV는 어떤 middle layer와도 연결 가능  
✅ **동적 변경**: 작업 중에도 parent 재할당 가능  
✅ **다중 제어 센터**: 상황에 따라 최적의 제어 센터 선택  
✅ **유선 강제**: 모든 경우에 항상 유선 통신 (force_parent_routing=true)

---

## 제약 사항

⚠️ **ROV는 항상 parent 필수**
```python
# 다음은 에러 발생:
PATCH /devices/3/connectivity-state
{
  "parent_id": null,  # ❌ ROV는 parent 필수
  "force_parent_routing": false
}
# ValueError: ROV must have parent_id for wired connection
```

✅ **항상 parent_id를 지정해야 함**
```python
# 올바른 방식:
PATCH /devices/3/connectivity-state
{
  "parent_id": 2,  # ✅ middle layer 지정
  "force_parent_routing": true
}
```

---

## 구현 코드

```python
# DeviceRegistry.update_device_connectivity_state()

if device.device_type == "ROV":
    # ROV: parent_id 반드시 필요 (어떤 middle layer든 가능)
    if parent_id is None:
        raise ValueError("ROV must have parent_id for wired connection")
    
    # 새로운 parent로 설정
    device.parent_id = parent_id
    
    # 유선 강제 활성화
    device.force_parent_routing = True
    
    # 타임스탐프 업데이트
    device.updated_at = utc_now()
```

---

## 테스트

```bash
# 1. ROV를 USV에 연결
curl -X PATCH http://localhost:8286/devices/3/connectivity-state \
  -H "Content-Type: application/json" \
  -d '{"parent_id": 2, "force_parent_routing": true}'

# 2. 현재 상태 확인
curl http://localhost:8286/devices/3

# 3. Control Ship으로 재할당
curl -X PATCH http://localhost:8286/devices/3/connectivity-state \
  -H "Content-Type: application/json" \
  -d '{"parent_id": 3, "force_parent_routing": true}'

# 4. 다시 확인
curl http://localhost:8286/devices/3
```

---

## 정리

- **ROV는 항상 유선 연결** (force_parent_routing=true)
- **Parent는 임의로 선택** 가능 (USV, Control Ship, 기타)
- **동적 변경 가능** (작업 중에도)
- **어떤 middle layer든** 사용 가능

기뢰 제거 작업 시 상황에 맞는 최적의 제어 센터를 선택하여 작업 효율을 극대화할 수 있습니다! 🚀
