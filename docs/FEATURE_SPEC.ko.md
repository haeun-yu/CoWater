# CoWater 기능 명세 및 사용 흐름

본 문서는 2026-05-06 현재 저장소 구현 기준으로 작성되었습니다. 기능은 `구현됨`, `부분 구현`, `향후 계획`으로 구분합니다.

## 1. 기능 상태 매트릭스

| 분류       | 기능                              | 상태      | 현재 기준 설명                                                                                                              |
| ---------- | --------------------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------- |
| 통합 관제  | 3D 해양 상황 시각화               | 구현됨    | `client/index.html`이 Three.js 기반 3D 대시보드를 제공합니다. Registry와 Moth 데이터를 반영합니다.                          |
| 통합 관제  | 실시간 healthcheck/telemetry 표시 | 구현됨    | Device Agent가 Moth로 healthcheck와 track telemetry를 발행하고, client가 WebSocket으로 구독합니다.                          |
| 통합 관제  | 신호등 기반 상태 표시             | 부분 구현 | UI 표시 개념으로 색상 상태를 사용합니다. 내부 표준 enum은 `INFORMATION`, `WARNING`, `CRITICAL`입니다.                       |
| 자율 임무  | 임무 생성 및 스케줄링             | 구현됨    | System Agent가 Alert/Event를 기반으로 Insight, Operation Plan, Mission Proposal, Approval, Mission을 생성합니다.           |
| 자율 임무  | 자율 임무 실행 및 추적            | 구현됨    | `task.assign` dispatch, device acceptance, `mission.result` 수신, Mission timeline/device execution result 기록이 구현되어 있습니다. |
| 자율 임무  | 임무 대체 및 경로 재계획          | 부분 구현 | System Agent가 reservation, queue, revalidation, 일부 reassign 흐름을 지원합니다. 전역 최적화는 없습니다.                   |
| 상황 인지  | 상황 인지형 관제                  | 구현됨    | `event.report` 수신 -> Event 저장 -> Alert 생성 -> Insight -> Plan/Proposal -> Approval -> Mission 반영 흐름입니다. |
| 상황 인지  | 자연어 기반 명령 인터페이스       | 향후 계획 | 현재 사용자-facing chatbot/Voice UI는 구현되어 있지 않습니다.                                                               |
| 상황 인지  | AI 기반 예측 정비                 | 향후 계획 | 배터리 임계값 기반 rule은 있으나, 예측 정비 모델은 구현되어 있지 않습니다.                                                  |
| Agent 관리 | Agent 자율성 레벨 관리            | 부분 구현 | config의 capabilities, constraints, LLM enabled 설정은 있으나 운영 UI 기반 자율성 레벨 관리는 없습니다.                     |
| Agent 관리 | 분산 시스템 모니터링              | 부분 구현 | Registry UI와 `/devices`, `/state` API로 연결 상태를 확인합니다. 별도 A2A graph 관제 UI는 없습니다.                         |
| Agent 관리 | 디바이스 생애주기 관리            | 구현됨    | 등록, agent attach/detach, healthcheck timeout, 삭제 API를 제공합니다.                                                      |

## 2. 사용자 역할

| 사용자 유형        | 현재 지원 범위                                                  | 향후 확장                                     |
| ------------------ | --------------------------------------------------------------- | --------------------------------------------- |
| 작전 지휘관        | Alert/Mission 상태 확인, 대응 흐름 검토                         | 자연어 임무 생성, 계획 승인, 임무 스케줄링 UI |
| 운영 관제사        | 3D 대시보드, 디바이스 상태, 경보 관리 화면 사용                 | 실시간 조치 옵션 승인 및 수동 재배정          |
| 현장 유지보수 인력 | 배터리, 연결 상태, healthcheck 기반 상태 확인                   | 예측 정비, 장비별 정비 이력 관리              |
| AI 엔지니어/개발자 | Agent state, Event/Alert/Mission ledger, A2A inbox/outbox 확인 | Agent trace, LLM 평가, 모델별 비교 도구       |

## 3. 현재 화면 구성

| 화면          | 파일                        | 현재 기능                                                                |
| ------------- | --------------------------- | ------------------------------------------------------------------------ |
| 3D 작전 뷰    | `client/index.html`         | 디바이스 3D 위치, depth, battery, heading, speed, alert 표시             |
| 경보 관리     | `client/alerts.html`        | Registry `/alerts`, `/insights`, `/approvals`, `/missions` 기반 경보/대응 확인 |
| 디바이스 상세 | `client/device-detail.html` | 특정 디바이스의 센서 stream, 위치, 배터리, 연결 상태 확인                |
| Registry UI   | `server/registration/ui/*`  | Registry API 기반 디바이스, alert, operation plan, approval, mission 화면 |

## 4. 현재 지원 시나리오

### 기뢰 탐지 이벤트 기반 대응

현재 구현에 가장 가까운 사용 흐름은 이벤트 기반 대응과 승인형 mission orchestration입니다.

| 단계 | 주체                               | 동작                                                                                              |
| ---- | ---------------------------------- | ------------------------------------------------------------------------------------------------- |
| 1    | Lower Agent 또는 테스트 클라이언트 | `mine_detection` 같은 Event를 `event.report`로 System Agent에 보고합니다.                         |
| 2    | System Agent                       | Event를 Registry Server의 Event ledger에 저장합니다.                                              |
| 3    | System Agent                       | `config.json > event_rules`를 기준으로 severity와 recommended action을 결정합니다.                |
| 4    | System Agent                       | Alert를 생성하고 Registry Server에 저장합니다.                                                    |
| 5    | System Agent                       | Insight를 만들고 필요 시 Operation Plan 또는 Mission Proposal을 생성합니다.                         |
| 6    | 사용자 / System Agent              | Approval을 결정하고 승인되면 Mission / Step / Task를 확정합니다.                                   |
| 7    | System Agent                       | 현재 연결된 capable device 중 대상 장비를 선택하고 middle relay 경로를 계산합니다.                 |
| 8    | Middle/Lower Agent                 | task를 수락 또는 거절하고, 수락 시 실행 후 `mission.result`를 상위로 보고합니다.                   |
| 9    | System Agent                       | Mission timeline, device execution result, 최종 상태를 갱신합니다.                                 |

## 5. 상태와 severity 기준

사용자-facing 문서에서는 Green/Yellow/Red를 직관적 표시 개념으로 사용할 수 있습니다. 단, 현재 구현의 canonical severity는 다음 enum입니다.

| 표시 개념 | 내부 severity                          | 의미                                      |
| --------- | -------------------------------------- | ----------------------------------------- |
| Green     | `INFORMATION` 또는 정상 connected 상태 | 추가 조치가 필요 없는 정보 또는 정상 상태 |
| Yellow    | `WARNING`                              | 주의가 필요한 상태                        |
| Red       | `CRITICAL`                             | 즉시 대응이 필요한 위험 상태              |

디바이스 연결 상태는 별도로 `connected` boolean과 healthcheck timeout으로 관리됩니다.

## 6. 예외 상황 / 제한 사항

현재 구현 기준의 예외 처리와 제한 사항은 다음과 같습니다.

| 예외 상황                            | 현재 처리                                                                                                                                                                         | 제한 사항 / 보완 필요                                                                                                               |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Registry Server 중단                 | Registry API가 응답하지 않으면 디바이스 등록, Event/Alert/Mission 원장 기록, 상태 조회가 실패합니다. 일부 Device Agent는 기존 identity cache로 Moth 초기화를 시도할 수 있습니다. | Registry가 canonical owner이므로 원장 기록과 assignment 계산은 Registry 복구 전까지 정상 보장되지 않습니다.                         |
| healthcheck 미수신                   | Registry healthcheck monitor가 timeout 기준으로 디바이스를 offline 처리합니다. 기본 기준은 1초 healthcheck, 3초 timeout입니다.                                                    | offline 판단은 healthcheck 기준입니다. telemetry만 수신되고 healthcheck가 없으면 Registry 위치/연결 상태가 stale해질 수 있습니다.   |
| Moth WebSocket 연결 실패             | Device Agent와 client는 재연결을 시도합니다. 핵심 A2A 명령 흐름은 HTTP를 사용하므로 Moth와 분리되어 있습니다.                                                                     | 실시간 3D 위치/센서 표시와 healthcheck 반영이 지연될 수 있습니다. 외부 Moth 서버 자체의 가용성은 저장소 내부에서 보장하지 않습니다. |
| A2A dispatch 실패                    | System Agent가 dispatch 결과를 Mission timeline과 device execution result에 기록하고, 실패 시 Mission을 `failed` 또는 후속 처리 상태로 갱신합니다.                                 | 네트워크 재시도 정책과 운영자 승인 UI는 제한적입니다. 실패 원인 분석은 timeline과 agent state 확인이 필요합니다.                    |
| capable device 없음                  | System Agent가 target을 찾지 못하면 Proposal 또는 Mission을 `failed` 또는 `needs_review`로 기록합니다.                                                                            | 임무 재계획 또는 사용자 수동 선택 UI는 아직 제한적입니다.                                                                            |
| capable device가 모두 reservation 중 | capability는 있으나 즉시 사용 가능한 장비가 없으면 Mission dispatch를 대기시키고, 이후 재검토합니다.                                                                              | queue는 최소 구현입니다. mission 간 preemption이나 전역 스케줄 최적화는 지원하지 않습니다.                                          |
| 중복 mission result                  | System Agent는 `mission_id + step_id + task_id + source_agent_id` 기준으로 중복 결과를 무시합니다.                                                                               | 중복 제거 기준 밖의 비정상 payload 정합성 검증은 추가 보완이 필요합니다.                                                            |
| step 실패 또는 부분 성공             | step evaluation 결과에 따라 다음 step 진행, retry, reassign, manual intervention, abort 중 하나로 판단할 수 있습니다.                                                             | 정책은 제한된 구현입니다. 모든 해양 임무 유형에 대한 평가 정책이 정의되어 있지는 않습니다.                                          |
| LLM/Ollama 응답 지연 또는 실패       | LLM 분석은 rule 기반 판단을 보조하는 비동기 hook입니다. 실패해도 rule/event 기반 흐름은 계속 동작합니다.                                                                          | 자연어 명령, 예측 정비, 복합 상황 분석은 아직 LLM 기반 운영 기능으로 완성되어 있지 않습니다.                                        |
| Agent 무한 루프 / 과도한 자율 행동   | 현재 구현은 config capabilities, constraints, rule 기반 판단, 명시적 A2A message type을 통해 행동 범위를 제한합니다.                                                              | 운영 UI에서 자율성 레벨을 세밀하게 제어하는 기능은 없습니다. 권한/승인 정책 고도화가 필요합니다.                                    |
| 실제 해양 환경 예측 불가             | 현재는 simulator와 이벤트 기반 PoC 중심입니다.                                                                                                                                    | 실제 센서, 실제 통신망, 장시간 운용, 악천후/장비 고장 데이터로 검증된 상태는 아닙니다.                                              |

## 7. 미구현 기능 및 계획

- 자연어/음성 명령 UI
- 사용자 입력 기반 임무 생성 및 실행 승인 화면
- 독립 Planner/Detect/Analyze/Report Agent 서비스 분리
- 예측 정비 모델과 정비 이력 관리
- 수백/수천 대 규모 부하 검증
- 3D 화면의 Agent graph node animation 및 A2A trace 시각화
