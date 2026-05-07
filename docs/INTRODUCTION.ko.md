# CoWater 프로젝트 소개서

본 문서는 2026-05-06 현재 저장소 구현 기준으로 작성되었습니다. 비전, 현재 구현, 향후 계획을 구분해 CoWater 프로젝트의 목표와 상태를 설명합니다.

## 1. 프로젝트 개요

**프로젝트명**: CoWater: 해양 무인체 운영 시스템

**목표**: 국제 해양 표준과 실시간 해양 데이터를 활용해 해역 전반을 통합 관제하고, 안전한 운항과 신속한 의사결정을 지원하는 Agentic AI 기반 해양 운영 플랫폼을 지향합니다.

**현재 상태**: CoWater는 완성형 운영 플랫폼이 아니라, 해양 무인체 협력 운용을 위한 멀티레이어 분산 에이전트 구조를 검증하는 PoC입니다.

현재 구현은 다음 구성요소를 중심으로 동작합니다.

| 구분            | 현재 구현                                                                               |
| --------------- | --------------------------------------------------------------------------------------- |
| Registry Server | 디바이스 등록, healthcheck 반영, parent assignment 계산, Event/Alert/Response 원장 제공 |
| System Agent    | `event.report` 수신, Event 저장, Alert 생성, Response 계획 및 A2A dispatch              |
| Device Agent    | USV/AUV/ROV/Control Ship 타입별 lower/middle agent 실행, telemetry/healthcheck 발행     |
| Moth telemetry  | 외부 Moth WebSocket을 통한 healthcheck 및 센서 stream 발행/구독                         |
| Dashboard       | 정적 HTML/JavaScript 기반 3D 관제 PoC 및 경보 관리 화면                                 |

## 2. 해결하려는 문제

CoWater가 해결하려는 문제는 다음과 같습니다.

- 다수 무인체의 위치, 배터리, 센서, 임무 상태를 한 곳에서 확인하기 어렵습니다.
- 개별 시스템이 분리되어 있으면 장애, 통신 저하, 임무 변경 시 대응 흐름이 늦어집니다.
- 사람이 모든 상태를 직접 해석하고 조치하면 의사결정 지연과 실수 가능성이 커집니다.
- 해양 운용에서는 통신 두절, 배터리 저하, 장비 고장, 미확인 위험물 같은 예외 상황을 시스템 차원에서 추적해야 합니다.

현재 PoC는 위 문제를 완전히 해결했다기보다, Event/Alert/Response 원장과 계층형 Agent dispatch를 통해 대응 흐름의 기본 구조를 검증합니다.

## 3. 현재 구현된 핵심 PoC

| 기능                         | 상태      | 설명                                                                                   |
| ---------------------------- | --------- | -------------------------------------------------------------------------------------- |
| 디바이스 등록 및 상태 관리   | 구현됨    | Registry Server가 디바이스, agent endpoint, 연결 상태, 위치, 배터리 정보를 관리합니다. |
| 계층형 Agent 구조            | 구현됨    | System Agent, Middle Agent, Lower Agent 구조를 사용합니다.                             |
| 실시간 healthcheck/telemetry | 구현됨    | lower/middle agent가 Moth WebSocket으로 healthcheck와 track telemetry를 발행합니다.    |
| Event/Alert/Response 원장    | 구현됨    | Registry Server가 canonical ledger 역할을 합니다.                                      |
| A2A 명령 dispatch            | 구현됨    | HTTP A2A `/message:send`로 `task.assign`, `mission.result` 등을 전달합니다.            |
| 3D 대시보드                  | 구현됨    | `client/index.html`이 Three.js 기반 3D 시각화를 제공합니다.                            |
| AI 기반 판단                 | 부분 구현 | Ollama 설정과 비동기 LLM 분석 hook이 있으나, 핵심 운영은 rule/event 기반입니다.        |
| 자연어/음성 명령             | 향후 계획 | 현재 사용자-facing 자연어/Voice UI는 구현되어 있지 않습니다.                           |

## 4. 기대 가치

CoWater의 기대 가치는 현재 검증된 PoC를 기반으로 다음 방향에서 확장될 수 있습니다.

| 가치        | 설명                                                                                                              |
| ----------- | ----------------------------------------------------------------------------------------------------------------- |
| 운영 효율성 | 디바이스 등록, 상태 수집, 경보 기록, 대응 배정을 일관된 흐름으로 처리합니다.                                      |
| 안전성      | `CRITICAL`, `WARNING`, `INFORMATION` severity를 기준으로 위험 이벤트를 추적하고 대응합니다.                       |
| 강건성      | Registry, System Agent, Middle/Lower Agent 책임을 분리해 일부 장애가 전체 정지로 이어지지 않는 구조를 지향합니다. |
| 확장성      | USV/AUV/ROV/Control Ship 외 다른 무인체 타입과 센서 track을 추가할 수 있는 구조를 둡니다.                         |

정량 효과, 예를 들어 "수십 배 효율" 같은 수치는 현재 저장소 구현만으로 검증되지 않았으므로 본 문서에서는 주장하지 않습니다.

## 5. 향후 확장 방향

다음 항목은 현재 구현 완료 기능이 아니라 향후 계획입니다.

- 자연어 및 음성 기반 명령 UI
- 임무 생성/승인/스케줄링 전용 화면
- 독립 Detect/Analyze/Report Agent 분리
- AI 예측 정비 고도화
- Docker Compose/Nginx 기반 분산 배포 구성
- React/Vue/TypeScript 기반 프론트엔드 전환
- Dry Navy, CoLand, CoForce 등 다른 도메인 확장
- Physical AI, World AI 등 장기 비전과 연계한 고도화
