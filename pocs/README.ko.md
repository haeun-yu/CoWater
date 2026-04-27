# CoWater PoC 워크스페이스

이 워크스페이스는 기존 통합형 CoWater 구조를 기능별로 분해한 독립 PoC 모음입니다. 각 PoC는 과거 전체 스택 없이도 실행하고 검토할 수 있어야 합니다.

## PoC 경계

| PoC | 목적 | 주요 출력 |
| --- | --- | --- |
| `01-device-streams` | 디바이스 멀티 스트림 생성 | `telemetry.*`, `sensor.*`, `device.event.*` JSONL |
| `02-device-agent-contract` | `usv`, `auv`, `rov`용 디바이스별 Agent 허브 | `ws://.../agents/{token}` |
| `03-device-registration-server` | 디바이스 등록과 주소 생성 | 디바이스 메타데이터 검증 |
| `04-realtime-dashboard` | 실시간 관제 UI | 지도/상태/경보 UI 프로토타입 |
| `05-control-ship-agent` | 중간 조정자 `control_ship` A2A 허브 | 하위 디스패치와 상위 상태 보고 |
| `06-control-center-system-agent` | 최상위 `control_center` A2A 허브 | 미션 계획과 직접 라우팅 |
| `07-mission-simulator` | 임무 시나리오 재생 | 시나리오 이벤트 JSONL |
| `08-command-control` | 승인, 권한, 명령 경로 검증 | `respond.command.*` |
| `09-report-learning` | 보고서와 피드백 루프 | 임무 요약과 학습 제안 |
| `10-mcp-detection` | MCP 기반 탐지 도구 호출 | Claude tool_use 분석 결과 |
| `11-a2a-interagent` | A2A 기반 에이전트 간 제안/적용 | rule update task 결과 |

## 실행 가능한 체인

현재 다음 PoC들은 독립 실행 가능합니다.

```bash
# 01: 멀티 스트림 디바이스 JSONL 생성
python3 pocs/01-device-streams/src/simulator.py --ticks 3 --output pocs/_out/device-streams.jsonl

# 02: 디바이스별 Agent 허브 실행
python3 pocs/02-device-agent-contract/device_agent_server.py

# 03: 디바이스 등록 및 메타데이터 조회
python3 pocs/03-device-registration-server/src/device_registration_server.py

# 05: control ship A2A 허브 실행
python3 pocs/05-control-ship-agent/device_agent_server.py

# 06: control center A2A 허브 실행
python3 pocs/06-control-center-system-agent/device_agent_server.py
```

## 위계 메모

현재 A2A 위계 데모는 `06-control-center-system-agent -> 05-control-ship-agent -> 02-device-agent-contract` 입니다.
독립 워크플로 PoC는 트리에 남아 있을 수 있지만, 더 이상 주 제어 경로 데모는 아닙니다.

## 규칙

- PoC끼리는 서로의 내부 구현을 import하지 않습니다.
- 공유 계약은 `packages/schemas`에만 둡니다.
- 통합은 파일, HTTP, WebSocket, 이벤트 버스를 통해서만 합니다.
- 각 PoC는 제외 범위를 명확히 적습니다.
- 기존 `services/` 스택은 재구축 중 참고용 legacy 자료로 취급합니다.
