# CoWater 핵심 아키텍처 원칙 및 운영 규칙

**문서 버전**: v0.1
**문서 목적**: CoWater의 Agent 구조, 역할과 책임, 운영 도메인, 통신 방식, Mission 처리, 상태 소유권, 자동 대응, 기록 규칙을 일관되게 정의한다.
**문서 성격**: 현재 구현 설명서가 아니라, 앞으로 CoWater 구현이 따라야 할 핵심 설계 기준 문서다.

---

## 1. 문서 사용 원칙

- 이 문서는 CoWater 구현의 기준이 되는 원칙과 규칙을 정의한다.
- 구현 세부사항은 이 문서의 원칙을 따라야 한다.
- 포트 번호, 실행 명령, 파일 경로, 특정 라이브러리 사용 방식은 별도 구현 문서에서 관리한다.
- 현재 구현과 다른 부분은 Gap으로 분리하여 관리한다.
- 이 문서는 기능 목록이 아니라 역할, 책임, 원칙, 규칙, 아키텍처 경계를 정의한다.

---

## 2. CoWater 정의

CoWater는 다양한 해양 무인체와 해양 데이터를 통합하여 실시간 상황 인식, 임무 관리, 위험 판단, 사용자 승인 기반 제어, 제한적 자동 대응을 제공하는 **AI Agent 기반 해양 무인체 통합 운영 플랫폼**이다.

CoWater는 단순 관제 시스템이 아니다.
CoWater는 디바이스의 역할, 운영 계획, Mission, Event, Alert, Agent 판단, 사용자 승인, 실행 결과를 연결하여 해양 무인체를 통합적으로 운영하는 플랫폼이다.

---

## 3. 시스템 핵심 목표

CoWater의 핵심 목표는 다음과 같다.

- 다수의 해양 무인체를 통합 운영한다.
- 각 디바이스의 역할과 운영 계획을 관리한다.
- 사용자 명령, 운영 계획, 이벤트, 위험 상황을 Mission으로 변환한다.
- System Agent가 Mission을 계획하고 조율한다.
- Device Agent가 자기 디바이스의 Task 수행 가능 여부와 실제 실행을 책임진다.
- 직접 통신이 어려운 디바이스는 Middle-layer Agent를 통해 운영한다.
- Critical 상황에서는 사전 정의된 정책에 따라 제한적 자동 대응을 수행할 수 있다.
- 정책이 없는 상황에서는 Agent가 추천은 할 수 있으나 사용자 승인 없이 자동 실행하지 않는다.
- 모든 중요한 판단, 승인, 거절, override, 실패, 결과를 기록한다.

---

## 4. 전체 아키텍처

CoWater는 다음 Agent 계층을 가진다.

```text
User
  ↓
System Agent Layer
  ↓
Middle-layer Agent Layer
  ↓
Device Agent Layer
  ↓
Physical Device / Vehicle / Sensor
```

### 4.1 구성 요소

| 구성 요소           | 설명                                                                                                  |
| ------------------- | ----------------------------------------------------------------------------------------------------- |
| User                | 운영 목표와 최종 결정을 내리는 주체                                                                   |
| System Agent        | 전체 운영 판단, Mission 생성, Task 분배, 사용자 승인 흐름을 담당하는 Agent                            |
| Middle-layer Agent  | System Agent와 직접 통신하기 어려운 Device Agent 사이를 연결하는 Agent                                |
| Device Agent        | 자기 디바이스의 상태, 센서, 수행 가능 작업, Task 실행을 책임지는 Agent                                |
| Registry Server     | 등록 정보, 연결 상태, Mission 상태, Event, Alert, Insight, Task 결과 등을 저장하는 공용 서버 컴포넌트 |
| Moth / Stream Layer | telemetry, healthcheck 등 실시간 데이터 스트림을 전달하는 계층                                        |
| Web UI              | 운영자가 상태, Mission, Alert, Agent 판단, 대응안을 확인하고 승인/수정/거절하는 화면                  |

---

## 5. 핵심 설계 원칙

### P1. Agent 직접 제어 원칙

각 Agent는 자기 자원만 직접 제어한다.

- System Agent는 디바이스 하드웨어를 직접 제어하지 않는다.
- Middle-layer Agent는 하위 디바이스를 임의로 직접 제어하지 않는다.
- Device Agent는 자기 디바이스만 직접 제어한다.
- 외부 대상과 상호작용하려면 반드시 해당 대상의 Agent와 통신해야 한다.

### P2. 책임 경계 명확화 원칙

System Agent가 모든 것을 검증하고 통제하지 않는다.
각 Agent는 자기 영역의 정보, 상태, 판단, 실행에 책임을 가진다.

### P3. 보고 기반 운영 원칙

System Agent는 Device Agent가 보고한 상태와 capability를 기준으로 운영한다.
보고되지 않은 정보를 임의로 추측하지 않는다.

### P4. Mission 중심 운영 원칙

CoWater는 단순 명령 전달 시스템이 아니라 Mission 중심 운영 플랫폼이다.

사용자 명령, Operation Plan, Event, Alert, 정책은 Mission 생성의 트리거가 될 수 있다.

### P5. Task 수행 가능성 최종 판단 원칙

Task를 실제로 수행할 수 있는지에 대한 최종 판단은 해당 Device Agent가 한다.

### P6. 정책 기반 자동 대응 원칙

사전 정의된 정책이 있는 Critical 상황에서는 제한적 자동 대응이 가능하다.
정책이 없는 상황에서는 Agent가 추천만 할 수 있으며 사용자 승인 없이 자동 실행하지 않는다.

### P7. 사용자 결정 우선 원칙

사용자 명령은 시스템 판단보다 우선될 수 있다.
단, System Agent는 위험을 경고하고 기록해야 하며, Device Agent는 물리적으로 수행 불가능한 Task를 거절할 수 있다.

### P8. 최소 중앙 상태 원칙

중앙 시스템은 모든 Raw Data와 센서 데이터를 지속 구독하지 않는다.
운영에 필요한 최소 상태, Event, Alert, Mission 상태, Task 결과를 중심으로 관리한다.

### P9. 기록 가능성 원칙

모든 중요한 판단, 승인, 거절, 수정, override, 실패, 결과는 추적 가능하게 기록되어야 한다.

### P10. 구현 세부 비노출 원칙

CoWater의 상위 운영 도메인은 Mission, Step, Task까지만 다룬다.
디바이스 내부 저수준 제어 명령은 Device Agent 내부 구현 세부사항으로 취급한다.

---

## 6. 용어 정의

| 용어                   | 정의                                                                                                                       |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Device                 | CoWater가 운영하는 물리 디바이스 또는 무인체. USV, AUV, ROV, UAV, Gateway, Sensor Node 등을 포함할 수 있다.                |
| Device Agent           | 각 디바이스에 존재하며 자기 디바이스의 정보, 상태, 센서 상태, 수행 가능 작업, Task 실행을 책임지는 Agent                   |
| Middle-layer Agent     | System Agent와 직접 통신하기 어려운 Device Agent 사이에서 등록, 상태, 데이터, Task 전달을 중계하는 Agent                   |
| System Agent           | CoWater 시스템 단에서 전체 운영 판단, Mission 생성, Task 분배, 사용자 승인 흐름을 담당하는 Agent                           |
| Registry Server        | 디바이스 등록 정보, 연결 상태, Agent 주소, Mission 상태, Event, Alert, Insight, Task 결과 등을 저장하는 공용 서버 컴포넌트 |
| Device Role            | 디바이스가 운영상 맡는 역할. 예: 순찰, 수중 데이터 수집, 통신 중계, 구조물 점검 대기                                       |
| Operation Plan         | Device Role을 기반으로 언제, 어떤 조건에서, 어떤 Mission을 생성하거나 실행할지 정의한 운영 계획                            |
| Operation Plan Trigger | Operation Plan을 실행시키는 조건. TIME, EVENT, CONDITION, MANUAL 유형을 가질 수 있다.                                      |
| Mission                | 실제 실행되는 임무 단위. 사용자 요청, Operation Plan, Event, Alert, 정책에 의해 생성될 수 있다.                            |
| Step                   | Mission 내부의 순서 있는 단계. 조건부 실행 또는 이전 Step 결과 의존성을 가질 수 있다.                                      |
| Task                   | 특정 Device Agent 또는 Middle-layer Agent에게 할당되는 작업 단위                                                           |
| Event                  | 실제로 발생한 사실. 예: 통신 두절, 센서 상태 변화, Task 완료, Mission 실패                                                 |
| Alert                  | 사용자가 알아야 하는 문제. System Agent가 Event를 해석하여 생성/관리한다.                                                  |
| Insight                | Agent의 판단, 분석, 추천 요약. 관련 Event, Alert, Mission과 연결될 수 있다.                                                |
| Healthcheck            | Agent의 생존 확인과 최소 운영 상태 확인을 위한 주기적 신호                                                                 |
| Telemetry              | 센서 또는 장비 데이터 스트림                                                                                               |
| A2A                    | Agent 간 직접 메시지 통신                                                                                                  |
| MCP                    | Agent가 외부 API 또는 도구를 구조화된 인터페이스로 호출할 때 사용하는 도구 접근 계층                                       |

---

## 7. Agent 역할과 책임

## 7.1 User

### 역할

User는 운영 목표와 최종 결정을 내리는 주체다.

### 책임

- Device Role을 설정한다.
- Operation Plan을 설정한다.
- System Agent에게 Role 또는 Operation Plan 추천을 요청할 수 있다.
- Mission 대응안을 승인, 수정, 거절할 수 있다.
- 자동 대응을 override할 수 있다.
- 주요 결정에 대한 결과를 책임진다.

### 규칙

- 현재 설계에서는 사용자 권한 체계를 다루지 않는다.
- 사용자는 단일 운영자로 본다.
- 사용자의 승인, 거절, 수정, override는 기록되어야 한다.

---

## 7.2 System Agent

### 역할

System Agent는 CoWater 전체 운영을 판단하고 조율하는 Agent다.

### 책임

- 사용자 명령을 해석한다.
- 사용자의 Device Role / Operation Plan 설정 요청을 수행한다.
- 사용자의 Device Role / Operation Plan 추천 요청에 대해 추천안을 생성한다.
- 사용자 명령, Operation Plan, Event, Alert, 정책을 Mission으로 변환한다.
- Mission을 Step과 Task로 구성한다.
- Task를 수행할 적절한 Device Agent 또는 Middle-layer Agent를 선택한다.
- 위험 상황을 판단한다.
- 대응안을 생성하고 사용자 승인을 요청한다.
- Mission 상태를 관리한다.
- Event, Alert, Insight를 관리한다.
- 주요 판단과 결과를 기록한다.

### 원칙

- System Agent는 전체 운영 판단과 조율을 담당한다.
- System Agent는 디바이스 하드웨어를 직접 제어하지 않는다.
- System Agent는 Device Agent가 보고한 정보를 기준으로 판단한다.
- System Agent는 보고되지 않은 디바이스 능력이나 상태를 임의로 추측하지 않는다.
- 정책이 없는 상황에서는 자동 실행하지 않는다.
- 사용자의 명령과 override는 시스템 판단보다 우선될 수 있다.

### 규칙

- 사용자가 Role / Operation Plan 설정을 요청하면 System Agent는 설정을 수행한다.
- 사용자가 Role / Operation Plan 추천을 요청하면 System Agent는 추천안을 생성한다.
- 추천안은 사용자 승인 후 적용한다.
- 사용자 명령, Operation Plan, Event, Alert는 Mission 생성의 트리거가 될 수 있다.
- Mission은 Step과 Task로 구성할 수 있다.
- Task는 Device Agent 또는 Middle-layer Agent에 할당한다.
- **Task를 Device에 할당할 때, System Agent는 다음을 모두 고려하여 최적의 Device를 선택한다:**
  - **Device의 가능한 작업 (available_actions) vs Task 요구 작업 (required_action): 매칭 확인**
  - **Device의 현재 위치 (latitude, longitude) vs Task 수행 위치: 거리 최소화**
  - **Device의 현재 배터리 상태 (battery_percent): 충분한지 확인**
  - **Device의 현재 상태 (connected, reservation_status): ONLINE 상태 확인**
  - Action alias 지원 (예: survey_depth ← scan_area, sonar_scanning)
- LOST / OFFLINE 상태의 Device Agent에는 신규 Task를 할당하지 않는다.
- 동일 문제 Alert는 fingerprint 기반으로 중복 생성하지 않는다.
- 사용자가 거절한 동일 추천은 일정 시간 반복하지 않는다.
- 모든 주요 판단과 결과는 기록한다.

---

## 7.3 Middle-layer Agent

### 역할

Middle-layer Agent는 System Agent와 직접 통신하기 어려운 하위 Device Agent 사이를 연결하는 Agent다.

### 책임

- 하위 Device Agent 등록 요청을 중계한다.
- 하위 Device Agent 상태를 System Agent에 전달한다.
- System Agent가 보낸 Task를 하위 Device Agent에 전달한다.
- 하위 Device Agent의 Task 결과를 System Agent에 전달한다.
- 데이터 전달과 통신 경로 유지를 담당한다.
- 하위 디바이스의 계층 구조를 System Agent가 알 수 있게 전달한다.

### 원칙

- Middle-layer Agent는 하위 Device Agent를 대신해 System Agent와 통신할 수 있다.
- Middle-layer Agent는 하위 Device를 임의로 직접 제어하지 않는다.
- 하위 Device 제어는 해당 Device Agent를 통해 수행한다.
- Middle-layer Agent는 기본적으로 중계와 상태 전달을 담당한다.
- 향후 System과 통신이 끊긴 상황에서 제한적 로컬 운영을 수행할 수 있다.

### 규칙

- 하위 Device Agent가 직접 등록할 수 없으면 Middle-layer Agent가 등록 요청을 중계한다.
- 등록 요청 시 Middle-layer Agent는 자신의 정보와 하위 Device 정보를 함께 전달한다.
- System Agent가 하위 Device에 Task를 보낼 때 직접 통신이 어렵다면 Middle-layer Agent를 통해 전달한다.
- 하위 Device Agent의 결과 보고도 Middle-layer Agent를 통해 System Agent에 전달될 수 있다.
- Middle-layer Agent의 로컬 소규모 운영은 현재 핵심 범위에서는 제한적으로만 다루고, 향후 확장으로 둔다.

---

## 7.4 Device Agent

### 역할

Device Agent는 자기 디바이스를 이해하고, 상태를 관리하며, 할당된 Task를 실제로 수행하는 Agent다.

### 책임

- 자기 디바이스 유형을 정확히 보고한다.
- 자기 센서 목록과 상태를 관리한다.
- 자기 디바이스가 수행 가능한 작업을 정확히 보고한다.
- 상태 변화가 발생하면 System Agent에 보고한다.
- Task를 받으면 수행 가능 여부를 판단한다.
- 수행 불가능한 Task는 이유와 함께 거절한다.
- 수행 가능한 Task는 실행하고 결과를 보고한다.
- 통신 두절 시 로컬 Failsafe 정책에 따라 행동한다.

### 원칙

- Device Agent는 자기 디바이스에 대한 1차 책임을 가진다.
- Device Agent는 자기 디바이스만 직접 제어한다.
- System Agent는 Device Agent를 통해서만 디바이스를 운영한다.
- Task 수행 가능 여부의 최종 판단은 Device Agent가 한다.
- 센서 상태 판단의 1차 책임은 Device Agent에 있다.
- 통신 두절 중 로컬 안전 행동은 Device Agent가 책임진다.

### 규칙

- Device Agent는 등록 시 자기 정보, 센서 목록, 수행 가능 작업, Agent 주소, 계층 정보를 보고한다.
- **Device Agent는 주기적 (기본: 1초마다) healthcheck를 통해 자신의 위치(latitude, longitude), 배터리 상태(battery_percent)를 Registry에 보고한다.**
  - 이를 통해 System Agent가 Task 분배 시 Device의 물리적 위치와 배터리 상태를 고려할 수 있게 한다.
  - Registry는 이 정보를 source of truth로 유지한다.
- **센서 상태 변화가 발생하면 A2A 메시지로 System Agent에 즉시 보고한다.**
  - 매번 healthcheck에 센서 상태를 포함하지 않고, 변화가 있을 때만 즉시 전달하여 통신량을 최소화한다.
- Device Agent는 센서 데이터를 지속적으로 System Agent에 보내지 않는다.
- Device Agent는 Task를 받으면 ACCEPTED 또는 REJECTED를 반환한다.
- REJECTED인 경우 reason을 함께 반환한다.
- Task 수행 결과는 COMPLETED, FAILED, CANCELED 등으로 보고한다.
- 실패 시 failure_category와 failure_message를 포함한다.
- 통신 두절이 발생하면 로컬 Failsafe 정책에 따라 행동한다.
- 통신 복구 후 주요 상태, Task 결과, 발생 Event를 System Agent에 보고한다.

---

## 8. 책임 경계와 금지 규칙

| 주체               | 금지                                                                                                              |
| ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| Registry Server    | Mission 판단, Task 대상 선정, Agent 제어, 디바이스 직접 명령                                                      |
| System Agent       | 디바이스 하드웨어 직접 제어, Device Agent가 보고하지 않은 상태/능력 임의 추측, 정책 없는 자동 실행                |
| Middle-layer Agent | 하위 Device 임의 직접 제어, System Agent 승인 없이 일반 Mission 생성, 하위 Agent 내부 상태 직접 조작              |
| Device Agent       | 다른 Device 직접 제어, 다른 Device 내부 상태 직접 조회, 자기 capability 과장 보고, 수행 불가능한 Task 무조건 수락 |
| User               | 현재 설계에서는 권한 체계를 정의하지 않는다. 단, 주요 결정과 override는 기록한다.                                 |

---

## 9. Device Role / Operation Plan / Mission 규칙

## 9.1 Device Role

Device Role은 디바이스가 운영상 맡는 역할이다.

예:

- 순찰 담당
- 수중 데이터 수집 담당
- 통신 중계 담당
- 구조물 점검 담당
- 대기/복구 담당

규칙:

- Device Role은 기본적으로 사용자가 설정한다.
- 사용자는 System Agent에게 Device Role 추천을 요청할 수 있다.
- System Agent의 추천은 사용자 승인 후 적용된다.

## 9.2 Operation Plan

Operation Plan은 Device Role을 기반으로 언제, 어떤 조건에서, 어떤 Mission을 생성하거나 실행할지 정의한 운영 계획이다.

Operation Plan은 단순 시간표가 아니다.
시간, 이벤트, 조건, 수동 실행을 모두 Trigger로 가질 수 있다.

Trigger 유형:

- TIME
- EVENT
- CONDITION
- MANUAL

예:

- 매일 09:00 A구역 순찰 Mission 생성
- AUV 스캔 완료 후 이상 객체가 있으면 ROV 정밀 촬영 Mission 생성
- ROV 작업 중이면 Gateway가 중계 위치 유지
- 특정 구역에 미확인 객체가 감지되면 확인 Mission 생성

규칙:

- Operation Plan은 기본적으로 사용자가 설정한다.
- 사용자는 System Agent에게 Operation Plan 추천을 요청할 수 있다.
- System Agent는 현재 디바이스 상태, 역할, capability, 운영 목적을 기준으로 추천안을 생성한다.
- 추천안은 사용자 승인 후 적용된다.
- Operation Plan Trigger가 충족되면 Mission이 생성될 수 있다.

## 9.3 Mission

Mission은 실제 실행되는 임무 단위다.

Mission 생성 트리거:

- 사용자 명령
- Operation Plan
- Event
- Alert
- 사전 정의된 Critical 정책
- System Agent 대응안

규칙:

- Mission은 Step을 가질 수 있다.
- Step은 순서와 조건을 가질 수 있다.
- Step은 이전 Step 결과를 입력으로 사용할 수 있다.
- Task는 특정 Device Agent 또는 Middle-layer Agent에게 할당된다.
- Mission 상태는 기록되어야 한다.
- Mission 실패 기준은 Mission Evaluation Policy에 따른다.

## 9.4 Step

Step은 Mission 내부의 순서 있는 단계다.

규칙:

- Step은 조건부로 실행될 수 있다.
- Step은 이전 Step 결과에 의존할 수 있다.
- Step 실행 결과가 failed여도 Evaluation Policy에 따라 다음 Step으로 진행할 수 있다.
- Step 종료 시 System Agent는 평가 결과를 기록할 수 있다.

## 9.5 Task

Task는 특정 Agent에게 할당되는 작업 단위다.

규칙:

- Task는 특정 Device Agent 또는 Middle-layer Agent를 대상으로 한다.
- Task는 고유한 task_id를 가진다.
- Task를 받은 Agent는 수행 가능 여부를 응답해야 한다.
- 수행 가능하면 ACCEPTED를 반환한다.
- 수행 불가능하면 REJECTED와 reason을 반환한다.
- Task 수행 후 결과를 보고한다.

---

## 10. Task 상태와 결과 규칙

Task는 최소 다음 상태를 표현할 수 있어야 한다.

- PENDING
- ASSIGNED
- ACCEPTED
- REJECTED
- RUNNING
- COMPLETED
- FAILED
- CANCELED

Task 결과는 최소 다음 정보를 포함할 수 있어야 한다.

- task_id
- status
- result_summary
- output_refs
- failure_category
- failure_message
- reported_at

실패 규칙:

- Task나 Mission이 실패하면 failure_category와 failure_message를 기록한다.
- 원인을 알 수 없으면 UNKNOWN으로 기록한다.
- 실패한 데이터는 삭제하지 않고 FROM_FAILED_TASK로 표시할 수 있다.

권장 failure_category:

- DEVICE
- COMMUNICATION
- SENSOR
- MISSION
- POLICY
- USER
- UNKNOWN

---

## 11. Task 중복 실행 방지 규칙

- 모든 Task는 고유한 task_id를 가진다.
- Device Agent는 자신이 처리한 task_id를 일정 기간 기억해야 한다.
- 동일 task_id를 다시 수신하면 중복 실행하지 않는다.
- 동일 task_id를 다시 수신한 경우 기존 결과 또는 현재 상태를 반환한다.
- 통신 복구 후 재전송되는 Task도 동일 task_id 기준으로 중복 실행을 방지한다.

---

## 12. Event / Alert / Insight 규칙

## 12.1 Event

Event는 실제로 발생한 사실이다.

예:

- Device connected
- Device disconnected
- Sensor status changed
- Task completed
- Task failed
- Mission failed
- Communication lost
- Safety action executed

규칙:

- Device Agent, Middle-layer Agent, System Agent는 Event를 생성할 수 있다.
- Device Agent는 문제나 상태 변화를 Event로 보고한다.
- Event는 Registry Server에 저장된다.

## 12.2 Alert

Alert는 사용자가 알아야 하는 문제다.

규칙:

- System Agent는 Event를 해석하여 필요 시 Alert를 생성한다.
- Device Agent는 원칙적으로 Alert보다 Event를 보고한다.
- System Agent가 Alert의 canonical 관리 주체다.
- Critical 로컬 자동 대응은 Device Agent가 즉시 수행할 수 있으며, 이후 Event로 보고한다.

## 12.3 Insight

Insight는 Agent의 판단, 분석, 추천 요약이다.

저장 항목:

- summary
- reason_summary
- severity
- recommended_action
- confidence_level
- related_event_id
- related_alert_id
- related_mission_id
- created_at

규칙:

- Insight는 Raw Data 전체가 아니라 판단 요약과 관련 ID 중심으로 저장한다.
- LLM prompt 전체나 긴 reasoning 전문을 저장하지 않는다.

---

## 13. Alert 중복 방지와 추천 반복 억제

## 13.1 Alert fingerprint

Alert는 fingerprint를 가진다.

fingerprint 생성 기준 예:

- affected_scope
- alert_type
- cause
- mission_id
- time_window

규칙:

- 동일 fingerprint의 Alert는 중복 생성하지 않는다.
- severity가 상승하면 기존 Alert를 갱신하거나 escalation한다.
- 새로운 근거가 생기면 기존 Alert를 갱신하거나 재알림할 수 있다.

## 13.2 추천 반복 억제

- 사용자가 특정 추천을 거절하면 동일 fingerprint의 추천은 일정 시간 suppress한다.
- suppress 기간 중에는 같은 추천을 반복하지 않는다.
- 단, severity가 상승하거나 새로운 근거가 생기면 다시 표시할 수 있다.

---

## 14. 통신 규칙

## 14.1 A2A 규칙

- Agent 간 의도적 상호작용은 A2A 메시지로 수행한다.
- System Agent는 Device Agent에게 저수준 제어 명령을 보내지 않는다.
- System Agent는 Task를 할당한다.
- Device Agent는 Task를 자기 디바이스가 수행 가능한 방식으로 해석하고 실행한다.
- 모든 A2A 메시지는 로깅되어야 한다.
- Task를 받은 Agent는 ACCEPTED 또는 REJECTED를 반환해야 한다.
- REJECTED인 경우 반드시 reason을 포함해야 한다.
- Task 수행 후에는 결과를 보고해야 한다.

## 14.2 MCP 규칙

- MCP는 Agent가 외부 API 또는 도구를 구조화된 인터페이스로 호출할 때 사용한다.
- Agent 간 명령, 이벤트, Task 전달은 MCP가 아니라 A2A를 사용한다.
- 공용 상태 조회와 기록은 Registry Server 또는 정해진 저장 계층을 따른다.

## 14.3 Healthcheck 규칙

- Healthcheck는 생존 확인과 최소 운영 상태 확인에만 사용한다.
- Healthcheck에 센서 상세 정보나 Raw Telemetry를 포함하지 않는다.
- Registry Server는 Healthcheck를 기준으로 Agent의 연결 상태를 관리한다.
- 구체적인 주기와 timeout 값은 구현 설정 문서에서 관리한다.

## 14.4 Telemetry 규칙

- Telemetry는 센서 또는 장비 데이터 스트림이다.
- Telemetry는 Registry Server의 canonical 상태 갱신 기준이 아니다.
- 대용량 Raw Data는 별도 스트림 또는 저장소로 관리한다.

---

## 15. Sensor Status 규칙

- 센서 상태의 1차 책임은 Device Agent에 있다.
- Device Agent는 자기 센서 상태를 관리한다.
- System Agent는 센서 데이터를 지속 구독하지 않는다.
- 센서 상태 변화가 발생하면 Device Agent는 SensorStatusChanged Event를 보고한다.
- System Agent는 보고받은 센서 상태를 Mission 판단에 참고할 수 있다.
- 센서 timeout, stale 판단, 신뢰도 모델은 현재 설계 범위에 포함하지 않는다.

최소 SensorStatus:

- sensor_id
- sensor_type
- status
- updated_at

---

## 16. 통신 두절 및 복구 규칙

- 통신 두절 시 Device Agent는 로컬 Failsafe 정책을 따른다.
- 통신 두절의 원인이 시스템 통신 문제라면 Device Agent는 Return Home, Return to Relay Zone, Return to Communication Recovery Point 등으로 복귀할 수 있다.
- 통신 문제가 아닌 제어 불능 상태라면 Device Agent는 문제 Event를 보고하고 가능한 안전 행동을 수행한다.
- System Agent는 LOST/OFFLINE 상태의 Device Agent에 신규 Task를 할당하지 않는다.
- 통신 복구 직후 Device Agent는 로컬 Mission/Task 상태, 완료/실패 결과, 주요 Event를 보고한다.
- System Agent는 Registry 상태와 Device Agent 보고 상태를 비교하여 Mission 상태를 동기화한다.
- 동기화가 완료되기 전에는 신규 Task를 할당하지 않는다.

---

## 17. 자동 대응 / 사용자 승인 / Override 규칙

## 17.1 자동 대응

- 사전 정의된 정책이 있는 Critical 상황에서는 제한적 자동 대응이 가능하다.
- 정책이 없는 상황에서는 Agent가 분석과 추천은 할 수 있으나 사용자 승인 없이 자동 실행하지 않는다.
- Device Agent는 자기 디바이스의 로컬 안전을 위해 즉시 행동할 수 있다.
- 예외 조치 후에는 반드시 상위 Agent 또는 System Agent에 Event로 보고해야 한다.

## 17.2 사용자 승인

- 고위험이거나 정책이 없는 대응안은 사용자 승인이 필요하다.
- 승인 화면에는 수행 계획, 대상 디바이스, 위험 요소, 예상 결과가 표시되어야 한다.
- 사용자는 승인, 수정, 거절, 취소를 선택할 수 있다.

## 17.3 사용자 Override

- 사용자는 자동 대응을 취소하거나 다른 명령을 내릴 수 있다.
- System Agent는 override 위험을 경고해야 한다.
- override는 기록되어야 한다.
- Device Agent가 물리적으로 수행 불가능하다고 판단한 Task는 사용자 명령이어도 거절될 수 있다.

---

## 18. Mission 실행 추적 규칙

사용자는 Mission이 어떻게 처리되고 있는지 전체 흐름을 볼 수 있어야 한다.

최소 추적 흐름:

```text
Mission 생성
→ Step 구성
→ Task 분해
→ Device 할당
→ Device 실행
→ 실행 상태 보고
→ 실행 결과 반환
→ Agent 해석
→ 사용자 확인
→ Timeline / Logs 저장
```

규칙:

- Mission 상세에는 현재 Mission 상태, 각 Step 상태, 각 Task 상태가 보여야 한다.
- 어떤 디바이스가 어떤 Task를 수행 중인지 보여야 한다.
- 실패하거나 중단된 Task의 이유를 볼 수 있어야 한다.
- Agent가 결과를 어떻게 해석했는지 확인할 수 있어야 한다.
- 사용자 승인/거절/재승인 내역을 Mission과 연결해 보여야 한다.
- Mission 전체 Timeline과 최종 Mission Result를 확인할 수 있어야 한다.

## 19. Device Execution Result 규칙

각 디바이스가 수행한 Task 결과는 사용자에게 확인 가능해야 한다.

최소 포함 정보:

- Device ID
- Task ID
- Task 상태
- 시작 시간
- 종료 시간
- 성공 / 실패 / 중단 여부
- 실패 사유
- 수행 위치
- 수집 데이터 요약
- 원본 데이터 참조
- 디바이스 상태 변화
- Device Agent 판단

규칙:

- Device Execution Result는 Mission / Step / Task와 연결되어야 한다.
- 원본 대용량 데이터는 별도 저장소에 둘 수 있으며 UI에는 요약과 참조만 노출할 수 있다.
- 실패 결과도 삭제하지 않고 기록해야 한다.

## 20. Mission Timeline 규칙

Mission 상세 화면에는 최소 다음 이벤트가 시간순으로 표시되어야 한다.

- Mission 생성
- 사용자 승인
- Step 시작
- Task 시작
- Device 결과 보고
- Agent 판단
- 경고 발생
- Plan 변경
- 사용자 재승인
- Task 완료
- Mission 완료 / 실패 / 중단

규칙:

- Timeline은 사후 분석이 가능할 정도로 충분한 문맥을 가져야 한다.
- 같은 이벤트를 여러 번 기록하는 경우 관련 ID와 이유를 남겨야 한다.
- Timeline은 Mission 상세 UI에서 직접 확인 가능해야 한다.

---

## 21. Mission Evaluation 규칙

Mission 또는 Step의 성공/실패 판단은 Evaluation Policy에 따른다.

기본 정책 예:

- ALL_STEPS_REQUIRED
- CRITICAL_STEP_REQUIRED
- MANUAL_REVIEW_ON_STEP_FAILURE
- REPLAN_ON_STEP_FAILURE

규칙:

- Step 실행 결과가 failed여도 Evaluation Policy에 따라 다음 Step으로 진행할 수 있다.
- 부분 성공 허용 여부는 Mission 또는 Step의 Evaluation Policy가 결정한다.
- 재계획 또는 중단 판단이 발생하면 그 근거를 기록한다.
- 수동 개입이 필요한 경우 Mission 상태는 manual_intervention_required 또는 이에 준하는 상태로 관리한다.

---

## 22. 상태 소유권

하나의 사실은 하나의 canonical owner를 가져야 한다.

| 정보                          | Canonical Owner                                        |
| ----------------------------- | ------------------------------------------------------ |
| Device 등록 정보              | Registry Server                                        |
| Device 연결 상태              | Registry Server                                        |
| Agent endpoint / routing 정보 | Registry Server                                        |
| Device Role                   | Registry Server                                        |
| Operation Plan                | Registry Server                                        |
| Mission / Step / Task 상태    | Registry Server                                        |
| Device의 로컬 Task 실행 상태  | 해당 Device Agent                                      |
| 센서 상태                     | Device Agent가 1차 소유, System은 보고받은 상태만 저장 |
| Event                         | Registry Server                                        |
| Alert                         | Registry Server                                        |
| Insight                       | Registry Server                                        |
| Task 결과                     | Registry Server                                        |
| A2A 통신 이력                 | 각 Agent 로그 / 필요 시 Registry 또는 Moth 시각화      |

상태 규칙:

- 같은 정보를 여러 위치에 유지하면 동기화 기준을 명시해야 한다.
- Registry 상태와 로컬 상태가 다를 수 있는 상황에서는 통신 복구 후 동기화 절차를 수행한다.
- System Agent는 Device Agent 내부 상태를 직접 조작하지 않는다.

---

## 23. Routing / Relay 규칙

- 직접 System Agent와 통신하기 어려운 Device Agent는 Middle-layer Agent를 통해 통신할 수 있다.
- System Agent는 Device Agent의 통신 경로를 Registry의 assignment 정보를 기준으로 판단한다.
- ROV, AUV 등 직접 통신이 어려운 디바이스는 Middle-layer Agent 경유가 기본이 될 수 있다.
- Middle-layer Agent가 offline이면 System Agent는 대체 Middle-layer Agent 또는 직접 경로를 검토한다.
- Middle-layer Agent는 하위 Device의 등록, 상태, Task, 결과를 중계할 수 있다.
- System Agent는 Middle-layer에 연결된 하위 Device에게도 Mission / Task를 할당할 수 있다.
- 이 경우 Middle-layer Agent는 임무를 자체적으로 재계획하지 않고, 명령 전달과 상태/결과 중계 역할을 수행한다.
- Middle-layer Agent가 자기 숙주 디바이스를 가진 경우 그 숙주 디바이스에 대해서만 직접 Task를 수행할 수 있다.

---

## 24. 기록 규칙

다음 항목은 반드시 기록되어야 한다.

- Device 등록
- Device Role 설정/변경
- Operation Plan 설정/변경
- Mission 생성
- Mission 승인/수정/거절/취소
- Task 할당
- Task ACCEPTED / REJECTED
- Task 완료/실패/취소
- Event 생성
- Alert 생성/갱신/해소
- Insight 생성
- 자동 대응 실행
- 사용자 override
- 통신 두절 및 복구
- Mission/Task 실패 원인

기록 원칙:

- 기록은 원인 추적과 사후 분석이 가능해야 한다.
- Raw Data 전체를 기록할 필요는 없다.
- 운영 판단에 필요한 요약, 관련 ID, 상태, 결과를 중심으로 기록한다.

---

## 25. 현재 설계에서 제외하는 범위

현재 핵심 설계에서는 다음을 제외한다.

- 사용자 권한 체계
- 사용자 역할별 권한 분리
- System Agent가 모든 센서 데이터를 지속 구독하는 구조
- 센서 timeout / stale 판단
- 복잡한 센서 신뢰도 모델
- 사용자 피드백 기반 모델 학습
- 자동 정책 개선
- Soul.md 기반 자동 개선 구조
- System Agent가 Device 내부 저수준 제어 명령을 직접 생성/실행하는 구조
- 복잡한 전역 스케줄 최적화

향후 확장 가능 항목:

- Soul.md / 정책 파일 / 지식 파일 기반 Agent 운영 지침 개선
- 기관별 Policy 관리
- 더 정교한 센서 신뢰도 모델
- Middle-layer Agent의 로컬 소규모 운영 강화
- 사용자 권한 체계
- 고도화된 Mission scheduling / preemption

---

## 26. 대표 운영 흐름

## 23.1 디바이스 등록 흐름

```text
Device Agent 실행
→ 자기 디바이스 정보 분석
→ 직접 통신 가능 시 System Agent 또는 Registry에 등록 요청
→ 직접 통신 불가능 시 Middle-layer Agent를 통해 등록 요청
→ System은 디바이스와 계층 구조 등록
→ Device Agent는 할당된 정보와 routing 정보를 로컬에 저장
```

## 23.2 사용자 명령 기반 Mission 흐름

```text
User 명령
→ System Agent 해석
→ Mission 필요 여부 판단
→ Step / Task 구성
→ 대응안 생성
→ User 승인
→ Task 할당
→ Device Agent 수행 가능 여부 판단
→ Task 수행
→ 결과 보고
→ Mission 상태 갱신
```

## 23.3 Operation Plan 기반 Mission 흐름

```text
Operation Plan Trigger 충족
→ System Agent가 Mission 생성 여부 판단
→ 필요 시 Mission 생성
→ Step / Task 구성
→ 사용자 승인 필요 여부 판단
→ Task 할당 및 실행
```

## 23.4 Event / Alert 기반 대응 흐름

```text
Device Agent 또는 Middle-layer Agent가 Event 보고
→ System Agent가 Event 해석
→ 필요 시 Alert 생성
→ 필요 시 Insight 생성
→ Mission 또는 대응안 생성
→ 사용자 승인 또는 정책 기반 자동 대응
→ Task 실행
→ 결과 기록
```

## 23.5 통신 두절 / 복구 흐름

```text
통신 두절 감지
→ System Agent는 Device를 LOST/OFFLINE으로 관리
→ Device Agent는 로컬 Failsafe 수행
→ 통신 복구
→ Device Agent가 로컬 상태/Task 결과/Event 보고
→ System Agent가 Mission 상태 동기화
→ 정상 운영 복귀
```

---

## 27. 리뷰 체크리스트

새 기능이나 구현 변경 시 다음을 확인한다.

- Agent 계층 구조를 위반하지 않는가?
- 각 Agent가 자기 숙주만 직접 제어하는가?
- System Agent가 디바이스를 직접 제어하지 않는가?
- Device Agent가 Task 수행 가능 여부를 최종 판단하는가?
- Role / Operation Plan / Mission / Step / Task 개념이 혼동되지 않는가?
- Operation Plan Trigger가 Mission 생성 조건으로 명확히 표현되는가?
- Event / Alert / Insight가 구분되는가?
- Alert 중복 방지를 위한 fingerprint가 있는가?
- 동일 Task 중복 실행을 방지하는가?
- 통신 복구 후 상태 동기화 규칙이 있는가?
- 사용자 승인/거절/override가 기록되는가?
- 정책이 없는 상황에서 자동 실행하지 않는가?
- 센서 데이터를 중앙에서 불필요하게 지속 구독하지 않는가?
- Registry Server를 Agent처럼 취급하지 않는가?
- 상태의 canonical owner가 명확한가?

---

## 28. 나쁜 예와 좋은 예

## 나쁜 예

- System Agent가 ROV 모터를 직접 제어한다.
- Registry Server가 직접 Device Agent에 Mission을 명령한다.
- Device Agent가 수행 불가능한 Task를 이유 없이 수락한다.
- Middle-layer Agent가 하위 Device 상태를 임의로 수정한다.
- Alert ID만 다르게 만들어 같은 문제를 계속 생성한다.
- 통신 복구 후 같은 Task를 중복 실행한다.
- 센서 데이터를 모두 중앙 서버가 지속 구독하려 한다.
- 정책이 없는 상황에서 Agent가 사용자 승인 없이 자동 실행한다.

## 좋은 예

- System Agent는 Task를 할당하고 Device Agent가 수행 가능 여부를 판단한다.
- Device Agent는 수행 불가능한 Task를 REJECTED와 reason으로 응답한다.
- Middle-layer Agent는 직접 통신이 어려운 Device Agent의 등록과 Task 전달을 중계한다.
- 동일 문제는 Alert fingerprint로 병합한다.
- 통신 복구 후 Device Agent가 로컬 상태를 보고하고 System Agent가 Mission 상태를 동기화한다.
- Operation Plan Trigger가 충족되면 Mission이 생성된다.
- 사용자가 Role/Plan 추천을 요청하면 System Agent가 추천안을 만들고 사용자 승인 후 적용한다.

---

## 29. 핵심 요약

CoWater는 Mission 중심의 AI Agent 기반 해양 무인체 통합 운영 플랫폼이다.

- System Agent는 전체 운영 판단과 Mission 조율을 담당한다.
- Middle-layer Agent는 직접 통신이 어려운 디바이스와 시스템을 연결한다.
- Device Agent는 자기 디바이스의 상태와 Task 실행을 책임진다.
- User는 운영 목표와 최종 결정을 담당한다.
- Device Role과 Operation Plan은 평시 운영의 기준이다.
- Mission은 실제 실행 단위이며 Step과 Task로 구성될 수 있다.
- System Agent는 Task를 할당하고, Device Agent는 Task를 자기 디바이스가 수행 가능한 방식으로 실행한다.
- 정책이 없는 상황에서 Agent는 추천할 수 있지만 자동 실행할 수 없다.
- 모든 중요한 판단과 결과는 기록되어야 한다.
