# Device Architecture

`device/`는 현장 실행기와 AI Agent의 경계를 분명히 나누는 것을 목표로 합니다.

## Layering

- `application/`: 런타임 조립과 진입점
- `agent/`: 의사결정, 상태, 미션/명령 처리
- `controller/`: HTTP, A2A, 외부 요청 입구
- `infrastructure/`: 플랫폼 결합, 디바이스 타입별 어댑터
- `simulator/`: 시뮬레이션 전용 실행체
- `tools/`: 센서, 제어, 보조 도구
- `storage/`: 디바이스 ID, 토큰, 짧은 지속 저장소
- `transport/`: Registry, Moth 같은 외부 연결

## Rules

- AI Agent는 플랫폼별 장비 구현에 직접 의존하지 않습니다.
- 실제 장비를 붙일 때는 `infrastructure/`와 `tools/`만 교체하거나 확장할 수 있어야 합니다.
- `controller/`는 얇게 유지하고, 판단과 상태 갱신은 `agent/`가 담당합니다.
- 재시작 후에도 필요한 식별 정보와 중복 방지 정보는 저장소에 남기고, 휘발성 실행 상태만 메모리에 둡니다.

## Integration Goal

나중에 실제 디바이스를 붙일 때는 AI Agent와 `agent/` 계층을 최대한 그대로 유지하고,
하드웨어/통신 어댑터만 바꾸는 구성을 목표로 합니다.

