# 02 Device Agent Architecture

이 POC는 디바이스별 Agent가 텔레메트리를 받아서 판단하고, 명령을 실행하는 흐름을 작게 쪼개서 보여줍니다.

## 구조

- `src/core/planner.py`
  - 들어온 telemetry를 정리해서 판단용 계획(plan)을 만듭니다.
- `src/core/decision.py`
  - plan 안의 후보들 중 최종 action을 고릅니다.
- `src/core/execution.py`
  - 선택된 action을 실제 command로 전송합니다.
- `src/core/feedback.py`
  - plan / decision / execution 결과를 세션 메모리에 남깁니다.
- `src/agents/`
  - USV, AUV, ROV별 추천 규칙을 담습니다.
- `src/transport/registry.py`
  - 세션, 웹소켓, 03 서버 동기화, 레이어 호출을 묶어서 관리합니다.
- `src/core/models.py`
  - 상태, 추천, 명령 요청의 공통 데이터 구조를 정의합니다.

## 실행 흐름

1. 01 시뮬레이터가 telemetry를 보냅니다.
2. `src/core/planner.py`가 데이터를 정리합니다.
3. `src/core/decision.py`가 어떤 action을 할지 고릅니다.
4. `src/core/execution.py`가 command를 전송합니다.
5. `src/core/feedback.py`가 결과를 기록합니다.

## 입력 경로별 처리 차이

### Device telemetry

- WebSocket stream으로 들어옵니다.
- `src/transport/registry.py`가 메시지를 받아서 `src/agents/`에 전달합니다.
- `src/agents/`는 디바이스 타입별 추천 후보를 만들고, 그 결과를 `core/planner -> core/decision -> core/feedback`이 보강합니다.

### User / upstream agent command

- HTTP `POST /agents/{token}/command`로 들어옵니다.
- 현재 구현에서는 이미 액션이 정해진 명령으로 보고 `src/core/execution.py`가 바로 전송합니다.
- 그 뒤 결과는 `src/core/feedback.py`가 기록합니다.

## 왜 비대칭인가

- telemetry는 해석이 필요한 입력이라 `planner`와 `decision`이 필요합니다.
- 사용자나 상위 Agent 명령은 이미 목적이 정해진 입력이라 보통은 바로 `execution`하는 편이 단순합니다.
- 이 PoC는 안전성과 단순성을 위해 이 비대칭 구조를 유지합니다.

## 현재 구조의 의미

- `src/agents/`는 추천을 만드는 판단 모듈입니다.
- `src/core/planner.py`는 입력을 정리합니다.
- `src/core/decision.py`는 후보 중 최종 action을 고릅니다.
- `src/core/execution.py`는 실제 command를 보냅니다.
- `src/core/feedback.py`는 결과를 남기는 기록 레이어입니다.

## feedback 레이어의 의미

- 현재 PoC에서 `feedback`은 외부가 평가를 돌려주는 의미가 아닙니다.
- `plan`, `decision`, `execution`의 결과를 세션 메모리와 context에 남기는 저널 역할에 가깝습니다.
- 나중에 실제 디바이스 ack, 성공/실패 응답, 재시도 결과, human feedback을 받게 되면 그때 진짜 feedback 루프로 확장할 수 있습니다.

원하면 나중에 사용자 명령도 `planner -> decision -> execution -> feedback`을 전부 통과하도록 완전 대칭 구조로 바꿀 수 있습니다.

## 판단 방식

- `llm` 설정이 있으면 내부적으로 hybrid 흐름을 사용합니다.
- `llm` 설정이 없으면 rule 기반 흐름을 사용합니다.

## 화면에서 보는 것

- Agent 상태
- 마지막 telemetry
- Planner / Decision / Execution / Feedback 결과
- 메모리와 추천 내역

이 구조는 프로덕션용 최종 설계라기보다, Agent의 기본 루프를 읽기 쉽게 보여주는 PoC 구성입니다.
