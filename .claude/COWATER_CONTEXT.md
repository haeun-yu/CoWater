# CoWater 프로젝트 컨텍스트

> 작업 전에 빠르게 훑는 참고 문서입니다. 정본은 `CONTEXT.md`, `docs/SYSTEM_ARCHITECTURE.md`, `docs/core/*`, `docs/scenarios/*`입니다.

---

## 빠른 이해

- CoWater는 해양 무인체를 다루는 AI 에이전트 기반 운영 플랫폼입니다.
- 핵심 구조는 `RequestHandler → MissionPlanner / PolicyManager → DeviceBridge → Device Agent`입니다.
- 운영 단위는 `Proposal → Mission → Task` 순서로 내려갑니다.
- `Device Agent`만 실제 Device를 직접 제어합니다.
- `DeviceBridge`는 Task 전달과 Device 보고 수집을 담당합니다.
- `PolicyManager`는 Rule과 Policy 기반 자동 대응을 담당합니다.
- `SystemSentinel`은 Heartbeat와 이상 징후를 감시합니다.

## 작업 시 항상 지켜야 할 언어

- `Proposal`: 사용자가 아직 승인하지 않은 해결안
- `Mission`: 승인 후 실제로 실행되는 임무
- `Task`: Mission 안의 개별 실행 항목
- `ABORTED`: Device Agent가 실행 전 거절
- `FAILED`: 실행 중 실패

## 어디를 읽어야 하는가

- 용어와 공통 언어: `CONTEXT.md`
- 전체 구조와 책임 경계: `docs/SYSTEM_ARCHITECTURE.md`
- 상태, 스키마, 이벤트: `docs/core/schema.md`, `docs/core/event-types.md`
- 절차와 흐름: `docs/scenarios/*.md`
- 구현 방법: `docs/implementation/*.md`

## 이 문서의 역할

- 개요만 제공
- 중복 설명은 하지 않음
- 세부 절차, 상태, 스키마, 구현 상세는 정본 문서로 이동
