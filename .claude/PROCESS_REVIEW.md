# 5-Agent 구조 프로세스 대응 검토

## 식별된 주요 프로세스 (CoWater lifecycle + operation)

| # | 프로세스 | 상세 | Linguistic | Mission Planning | Policy | Reporting | Supervisor | 이슈 |
|---|---------|------|-----------|-----------------|--------|-----------|-----------|------|
| 1 | **사용자 입력** | 자연어 명령어 수신 | ✅ 수신 & NLU | | | | | |
| 2 | **Intent 분류** | MISSION/QUERY/UPDATE/DELETE/CONTROL | ✅ 분류 | | | | | |
| 3 | **Entity 추출** | @@device, @@sensor 파싱 | ✅ 추출 | | | | | |
| 4 | **권한 검증** | ADMIN/OPERATOR/VIEWER | ✅ 검증 | | | | | |
| 5 | **Capability Matching** | Device.actions[] 매칭 (MISSION intent) | | ✅ | | | | |
| 6 | **Proposal 생성** | 여러 안 제시 (ADR-002) | | ✅ | | | | |
| 7 | **Proposal 선택 & 승인** | 사용자 선택 | | ✅ (감시) | | | | |
| 8 | **상태 재검증** | Proposal 승인 후 Device/Agent 확인 | | ✅ | | | | |
| 9 | **Mission 생성** | Proposal → Mission | | ✅ | | | | |
| 10 | **Task 할당** | Device에 Task 배정 | | ✅ | | | | |
| 11 | **Task 실행** | Device Agent 작업 수행 | | | | | ✅ (감시) | |
| 12 | **Heartbeat 모니터링** | Device 상태 주기적 확인 | | | | | ✅ | |
| 13 | **신호 강도 감시** | signal_strength < 30% | | | | | ✅ | |
| 14 | **배터리 감시** | battery_percent 추적 | | | | | ✅ | |
| 15 | **실시간 통신 전환** | 환경 변화 → active_mediums 갱신 | | | ✅ | | ✅ | Agent 협력? |
| 16 | **AgentConnection 재검증** | 물리 통신 유효성 확인 | | | ✅ | | | |
| 17 | **Policy 기반 응답** | ENV_STATE_CHANGED 이벤트 → 정책 실행 | | | ✅ | | | |
| 18 | **Config/Rule 수정** | UPDATE intent | | | ✅ | | | |
| 19 | **Anomaly Detection** | 신호 손실, 배터리 부족 등 감지 | | | | | ✅ | |
| 20 | **자동 응답 액션** | EMERGENCY_SURFACE 미션 생성 등 | | | ✅ (정책) | | ✅ | Policy vs Supervisor? |
| 21 | **Task 결과 기록** | Task 완료/실패 이벤트 | | | | ✅ | ✅ (감시) | 중복? |
| 22 | **히스토리 조회** | QUERY intent → 과거 기록 조회 | | | | ✅ | | |
| 23 | **Report 생성** | 리포트 출력 (QUERY) | | | | ✅ | | |
| 24 | **Archive 관리** | Mission 완료/실패 후 보관 | | | | ✅ | | |
| 25 | **통신 복구 처리** | Device 재연결 → 상태 동기화 | | ✅ (Task) | | ✅ (기록) | ✅ (감시) | **협력 프로세스** |
| 26 | **Device 제거** | Device REMOVED 상태 | | ✅ (Task 취소) | | | | **DELETE intent?** |
| 27 | **Device AgentConnection 재구성** | Device 제거 시 대체 Agent 찾기 | | ✅ | | | | |
| 28 | **권한 거절** | 사용자 권한 부족 시 | | | | | | Linguistic이 충분? |

---

## 미대응 프로세스 (❌ 불명확)

### 1️⃣ **DELETE Intent 처리** (Row 26)
사용자가 "ROV-1 제거해줘"라고 요청할 때:
- Device 상태 확인 (OFFLINE 필수)
- AgentConnection 영향도 분석
- 진행 중인 Task 취소
- Device 제거 처리

**현재**: 누가 담당하나?
- Policy Agent? (규칙이지만 Device 제거는 Policy 이상)
- 새로운 System Admin Agent?
- Mission Planning? (Task 취소 관련)

**제안**: Policy Agent가 DELETE intent를 받아서 처리할지, 아니면 별도 처리?

### 2️⃣ **통신 복구 & 상태 동기화** (Row 25 - 핵심!)
Device 재연결 시 복잡한 협력 필요:

```
Device 복구 메시지 수신 (completed_tasks[], in_progress_task)
  ↓
1️⃣ Task 상태 갱신 (Mission Planning?)
2️⃣ Mission 상태 갱신 (Mission Planning?)
3️⃣ 모든 이벤트 기록 (Reporting?)
4️⃣ Anomaly 해제 (Supervisor?)
5️⃣ 새로운 Task 할당 가능? (Mission Planning?)
```

**문제**: 여러 Agent이 동시에 개입하는데, **조율이 필요**하지 않나?

예시:
- Reporting이 먼저 이벤트 기록하면, Mission Planning의 Task 상태 갱신과 타이밍 충돌 가능?
- Supervisor가 ONLINE 이벤트 감시하면서 동시에 Mission Planning이 새 Task 할당하면?

### 3️⃣ **Anomaly Detection → 자동 응답** (Row 20)

```
signal_strength < 30% 감지 (Supervisor)
  ↓
EMERGENCY_SURFACE 미션 생성
  ↓
누가 미션을 생성하나?
```

**현재 분배**:
- Supervisor: anomaly.detected 이벤트 발행
- Policy: anomaly 기반 rule 실행 → EMERGENCY_SURFACE 정책 적용

**문제**: 
- Policy가 "정책 실행"하는 것과 "새로운 미션 생성"하는 것은 다른가?
- EMERGENCY_SURFACE는 즉시 실행되어야 하는데, Policy에서 미션을 생성할 권한이 있나?

### 4️⃣ **권한 거절** (Row 28)

```
Linguistic: "권한 부족입니다" → 실제로 어떤 Agent이 권한 검증?
```

**현재**: Linguistic이 사용자 레벨 권한은 체크하지만,
- Device/Agent 레벨 접근 권한은? (예: "ROV-1에 접근 권한이 없습니다")
- Entity-level permission은 어디서 확인?

---

## ⚠️ 확인 필요 사항

### A. **Policy vs Supervisor의 책임 경계**

| | Policy | Supervisor |
|---|--------|-----------|
| **감시** | ❓ | ✅ anomaly 감지 |
| **자동 응답 결정** | ✅ rule 실행 | ❓ |
| **미션 생성** | ❓ | ❓ |
| **상태 변경** | ✅ config/rule 적용 | ❓ |

**예시 충돌**:
```
signal_strength < 30% 감지
  ↓
Supervisor: anomaly.detected 이벤트 발행
  ↓
Policy: rule 매칭 → EMERGENCY_SURFACE 적용
  ↓
문제: 누가 실제로 "EMERGENCY_SURFACE 미션"을 생성하나?
  - Policy가 생성? → Policy의 책임이 너무 커짐
  - Supervisor가 생성? → Supervisor도 action.triggered 발행
  - 별도 Agent?
```

### B. **통신 복구 시 Agent 간 조율**

```
Device 복구 메시지 (Task 완료 정보 포함)
  ↓
1️⃣ Mission Planning: Task 상태 갱신
2️⃣ Reporting: 모든 이벤트 기록
3️⃣ Supervisor: ONLINE 이벤트 감시 → anomaly 해제
4️⃣ Policy: 새 Task 할당 가능 정책 적용
  ↓
순서가 중요한데, Event-Driven으로 충분?
```

### C. **DELETE intent의 위치**

```
사용자: "ROV-1 제거해줘"
  ↓
Linguistic: DELETE intent 분류
  ↓
누가 처리?
  - Policy Agent? → Device 제거, Task 취소, AgentConnection 재구성
  - 기존 Agent들로 부족한가?
```

---

## 현재 상태 정리

✅ **충분히 대응하는 부분**:
- User input → intent classification → Capability matching
- Proposal generation & selection
- Task execution & heartbeat monitoring
- Query & reporting
- Single event 기반 rule 실행 (예: rule.if.signal_strength < 30% → rule.then.ALERT)

❌ **불명확한 부분**:
1. **복합 프로세스** (통신 복구, device 제거) → Agent 간 조율 메커니즘 불명확
2. **Policy vs Supervisor** → 자동 응답 중에서 누가 "새 미션 생성"할지 불명확
3. **DELETE intent** → 처리 Agent 불명확

---

## 질문

1. **통신 복구 시 Agent 간 순서 보장이 필요한가?**
   - 만약 필요하면, Coordinator Agent가 필요할 수도?
   - 아니면 Event 타임스탬프로 충분?

2. **EMERGENCY_SURFACE 같은 "자동 생성 미션"은 누가 생성하나?**
   - Supervisor가 action.triggered 이벤트 발행 후, Policy가 구독해서 미션 생성?
   - 아니면 Supervisor가 직접 Mission Planning 호출?

3. **DELETE intent는 Policy Agent가 처리할까?**
   - 아니면 별도 System Admin 기능?

4. **Linguistic Agent의 권한 검증은 충분한가?**
   - User-level only? 아니면 Entity-level도?
