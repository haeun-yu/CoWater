# Backend Architecture

이 저장소의 서버는 두 개의 큰 축으로 나뉩니다.

## `registration`

시스템의 원장(source of truth)입니다.

- `src/api.py`: HTTP API와 lifespan, 웹소켓, 외부 발행 진입점
- `src/application/`: 런타임 조립과 구성요소 생성
- `src/domain/`: 도메인 모델의 공개 경계
- `src/infrastructure/`: DB, 스키마, 외부 저장/발행 어댑터
- `src/registry/`: 실제 저장과 조회를 담당하는 persistence 구현

이 서비스는 디바이스, 알림, 이벤트, 정책, 승인, 미션 메타데이터를 DB 중심으로 보관합니다.

## `system-agent`

AI Agent가 들어있는 실행 계층입니다.

- `agent/`: 추론, 정책 평가, 미션 생성, 상태 머신, 시뮬레이터, 실행 루프
- `controller/`: HTTP/A2A 진입점
- `application/`: AgentRuntime 조립과 부팅
- `domain/`: Agent 상태의 공개 경계
- `infrastructure/`: Registry 같은 외부 시스템 연결
- `transport/`: 실제 HTTP/REST 통신 구현

이 서비스는 “판단”과 “조율”을 맡고, registration을 통해 저장과 조회를 일관되게 처리합니다.

## 설계 원칙

1. 저장이 필요한 데이터는 DB를 우선 사용합니다.
2. 메모리는 휘발성 상태와 실행 중 캐시만 둡니다.
3. AI Agent의 추론, 외부 통신, HTTP 입구는 서로 분리합니다.
4. entrypoint는 얇게 유지하고, 조립은 `application`에서 처리합니다.
