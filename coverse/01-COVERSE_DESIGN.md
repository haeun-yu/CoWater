# CoVerse: 상황인식 논리적 데이터 공간

## 개요

**CoVerse**는 상황인식을 위한 **논리적 데이터 공간 기술**입니다.

**핵심 원칙:**
- 현실 공간을 그대로 복제하는 것이 아니라, **운영자의 판단에 필요한 데이터를 목적 중심으로 재구성**
- 3D는 선택지일 뿐, 2D, Graph, Timeline, Report 등 **다양한 View로 표현 가능**
- **Data와 Viz는 완전히 분리**: 같은 논리적 데이터를 여러 시각화 방식으로 표현
- **정적 데이터(설정, 자산)와 실시간 데이터(센서, 이벤트)를 구분**

**CoVerse의 범위:**
이 문서는 **범용 CoVerse 설계**를 정의합니다. CoWater는 이를 해양 무인체 운영 도메인에 인스턴스화한 사례입니다.

---

## 데이터 레이어 구조

CoVerse는 다음 5개 논리적 레이어로 구성됩니다:

### 1. Entity Layer (관리 대상 자체)

**역할**: 시스템이 관리하는 실체(엔티티)의 현재 상태와 속성입니다.

**포함 내용:**
- 엔티티 ID, 이름, 타입
- 현재 상태 (정상, 오류, 유휴 등)
- 실시간 센서/측정값
- 연결 상태, 신호 강도
- 마지막 통신 시간

**데이터 특성:**
- 주로 **실시간 데이터** (높은 빈도, 초 단위)
- 각 엔티티별 독립적
- 예: 무인체 위치, 배터리, 센서값 / 서버 CPU, 메모리 / 센서 온도, 습도

---

### 2. Operation Layer (의도 & 실행)

**역할**: 시스템이 실행하는 작업들과, 각 작업에 대한 의도적 결정입니다.

**구조: 2단계**

**2-1. Mission (상위 목표)**
- Mission ID, 목표, 우선도
- Mission 상태 (계획, 할당, 진행중, 완료, 실패)
- 예상 완료 시간, 구성 Task 목록

**2-2. Task (구체적 작업)**
- Task ID, 타입, 상태
- 할당된 엔티티, 실행 명령
- 진행 상황, 진행률
- 작업 결과 (성공/실패 사유)

**2-3. Decision Trail (판단 근거)**
각 Task/Mission에 대해 시스템이 내린 판단의 **근거와 이유**:
- 판단 ID, 판단 종류 (할당, 우선도 조정, 종료 등)
- 판단을 내린 역할 (예: 분석 역할, 통제 역할)
- 판단의 근거 데이터 (어떤 센서값, 이벤트 때문인지)
- 판단 시점, 신뢰도
- 판단 결과

**데이터 특성:**
- 중간 빈도 업데이트 (초~분 단위)
- 시스템과 엔티티 간의 명령/응답
- **Decision Trail은 운영자의 상황 인식에 필수** (왜 그런 결정을 했는가를 이해하기 위해)

---

### 3. System Layer (시스템 건강도)

**역할**: 시스템 자체의 상태와 성능, 그리고 운영 효율성입니다.

**포함 내용:**
- 시스템 컴포넌트 상태 (정상, 과부하, 에러, 연결 끊김)
- 성능 지표 (CPU, 메모리, 지연 시간, 처리량)
- 에러/알람 (임계값 초과, 비정상 패턴 감지)
- 시스템 이벤트 (컴포넌트 재시작, 설정 변경 등)
- 운영 부하 (현재 처리 중인 작업 수, 대기열 크기)

**데이터 특성:**
- 실시간 모니터링 데이터 (높은 빈도, 초 단위)
- 시스템 전체의 운영 상황을 반영
- 예: Agent 상태, Database 연결, Message Broker 처리량 / 센서 네트워크 품질, 통신 대역폭

---

### 4. Temporal Layer (시간 흐름)

**역할**: 시스템에서 일어난 모든 이벤트와 상태 변화의 기록입니다.

**포함 내용:**
- 이벤트 로그 (뭐가, 언제, 어디서, 왜 일어났는가)
- 상태 변화 (Entity, Task, System 상태 전이)
- 타임스탠프와 시퀀스
- 타임라인 (시간 순서대로 정렬된 이벤트)
- 히스토리 (완료된 Task, 해결된 Alert, 패턴)

**데이터 특성:**
- 주로 **저장 데이터** (낮은 빈도, 이벤트 기반)
- 추후 분석, 학습, 감시용
- 예: "13:45에 무인체 A가 배터리 부족 감지, 14:00에 Task 할당, 14:30에 완료"

---

### 5. Spatial Layer (공간 & 관계)

**역할**: 엔티티들 간의 공간적 관계입니다.

**포함 내용:**
- 엔티티 위치 (좌표, 고도, 깊이 등)
- 엔티티 간 거리/근접성
- 엔티티 간의 계층 관계 (예: 작은 그룹이 모여 큰 그룹을 이룸)
- 공간적 클러스터링 (비슷한 특성의 엔티티들이 근처에 있는가)

**데이터 특성:**
- Entity Layer에서 파생된 데이터
- 중간 빈도 업데이트
- 상황 인식 (엔티티 군 관계)용
- 예: 무인체 그룹의 분산도, 서로 간 거리 / 센서 네트워크의 커버리지 밀도

---

## 데이터 흐름 개요

```
[Entity] (실체)
   ↓ (실시간 상태, 센서값)
[Entity Layer]
   ↓
[Monitoring Role] (이상 감지)
   ↓
[Analysis Role] (분석, 우선도 결정)
   ↓
[Decision Trail] (판단 근거 기록)
   ↓
[Control Role] (명령 결정)
   ↓
[Operation Layer] (Task/Mission 생성)
   ↓
[Entity] (명령 실행)

[System Monitoring Role] (병렬)
   ↓
[System Layer] (시스템 건강도)

[All Roles]
   ↓ (이벤트 발생)
[Temporal Layer] (기록)
   ↓
[Analysis Role] / [Learning Role] (분석, 개선)
```

**핵심**: 각 "Role"은 논리적 역할이며, 구현 시 하나의 에이전트일 수도, 여러 에이전트일 수도 있습니다.

---

## 구현 전략

### Phase 1: 기반 구조
- CoVerse Data Model 정의 (각 레이어의 스키마, Role 인터페이스)
- Data Collection 로직 (각 출처에서 데이터 수집)
- Data Aggregation 로직 (모든 데이터를 통합 공간에 모으기)
- Decision Trail 저장소 (각 판단의 근거를 기록하는 방식)

### Phase 2: Single View 구현
- **전체 상황을 표현하는 하나의 View** (2D, 3D, Graph 중 선택)
- 이 View는 CoVerse의 모든 5개 레이어를 시각화

### Phase 3: Multi-View 지원 (선택사항)
- 여러 View 방식 추가 (Timeline, Report, Network Graph 등)
- 같은 CoVerse 데이터를 다양한 관점으로 표현

### Phase 4: Part Streaming (선택사항)
- 사용자 인터렉션 시 필요한 데이터만 전달
- 시스템 자원 최적화

---

## CoVerse vs. 구현체 (CoWater 예시)

| 개념 | CoVerse (범용) | CoWater (인스턴스) |
|------|---|---|
| Entity | 관리되는 실체 | 무인체, 센서 |
| Monitoring Role | 이상 감지 역할 | Detection Agent |
| Analysis Role | 분석 역할 | Analysis Agent |
| Control Role | 통제 역할 | Control Agent |
| System Monitoring | 시스템 감시 역할 | Supervision Agent |
| Operation | Task/Mission | 해양 무인체 Task/Mission |

---

## 다음 단계

1. ✅ 범용 CoVerse 레이어 정의 완료
2. 📋 CoVerse Data Schema 정의 (`02-DATA_SCHEMA.md`)
3. 📊 Data Flow & Decision Trail 상세 분석 (`03-DATA_FLOW.md`)
4. 🏗️ CoWater 인스턴스화 계획 (`04-COWATER_MAPPING.md`)
5. 💻 구현 시작
