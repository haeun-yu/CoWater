# CoWater PoC 워크스페이스

이 워크스페이스는 기존 통합형 CoWater 구조를 기능별로 분해한 독립 PoC 모음입니다. 각 PoC는 과거 전체 스택 없이도 실행하고 검토할 수 있어야 합니다.

## PoC 경계

| PoC | 목적 | 주요 출력 |
| --- | --- | --- |
| `01-device-streams` | 디바이스 멀티 스트림 생성 | `telemetry.*`, `sensor.*`, `device.event.*` JSONL |
| `02-bridge-normalizer` | 원시 프로토콜을 정규화된 스트림으로 변환 | `DeviceStreamMessage` |
| `03-device-registration-server` | 디바이스 등록과 주소 생성 | 디바이스 메타데이터 검증 |
| `04-realtime-dashboard` | 실시간 관제 UI | 지도/상태/경보 UI 프로토타입 |
| `05-detection-agents` | 스트림을 도메인 탐지 이벤트로 변환 | `detect.*` |
| `06-agent-workflow` | `detect -> analyze -> respond` 흐름 검증 | 분석 이벤트와 경보 후보 |
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

# 02: 원시 프로토콜 fixture 정규화
python3 pocs/02-bridge-normalizer/src/normalizer.py --protocol ros-navsat --input pocs/02-bridge-normalizer/sample-data/raw-ros-navsat.json

# 03: 디바이스 등록 및 메타데이터 조회
python3 pocs/03-device-registration-server/src/device_registration_server.py

# 05: sonar contact에서 기뢰 의심 이벤트 탐지
python3 pocs/05-detection-agents/src/detect.py --input pocs/_out/device-streams.jsonl --threshold 0.4 > pocs/_out/detect-events.jsonl

# 06: detect.mine을 분석 이벤트와 경보 후보로 변환
python3 pocs/06-agent-workflow/src/workflow.py --input pocs/_out/detect-events.jsonl
```

## 규칙

- PoC끼리는 서로의 내부 구현을 import하지 않습니다.
- 공유 계약은 `packages/schemas`에만 둡니다.
- 통합은 파일, HTTP, WebSocket, 이벤트 버스를 통해서만 합니다.
- 각 PoC는 제외 범위를 명확히 적습니다.
- 기존 `services/` 스택은 재구축 중 참고용 legacy 자료로 취급합니다.
