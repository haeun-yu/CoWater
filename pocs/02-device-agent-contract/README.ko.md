# 02 Device Agent Contract

이 POC는 `usv`, `auv`, `rov`를 위한 디바이스별 Agent 허브입니다.
각 디바이스 타입은 별도 Agent 클래스로 분리됩니다: `USVAgent`, `AUVAgent`, `ROVAgent`.
LLM이 설정되어 있으면 hybrid 방식으로 판단하고, LLM이 없으면 rule 기반으로 판단합니다.

## 하는 일

- `ws://<host>:<port>/agents/{token}` 형태로 디바이스 WebSocket 연결을 받습니다.
- POC 01에서 쓰는 스트림 envelope/payload를 그대로 받아 처리합니다.
- 등록 `token`을 Agent 세션 identity로 사용합니다.
- 스트림 전에 `hello` 메시지로 device identity를 먼저 받습니다.
- `hello` 이후에는 03 서버에 Agent 연결 정보를 다시 등록합니다.
- 텔레메트리는 먼저 Decision Layer를 거쳐 판단됩니다.
- 디바이스 타입별로 간단한 추천 액션을 돌려줍니다.
- REST로 Agent 상태를 조회할 수 있습니다.
- 세션에 허용 작업 목록(`available_actions`)을 저장하고, 대시보드에서는 버튼만 표시합니다.
- 세션마다 LLM 사용 여부를 대시보드에서 확인할 수 있습니다.
- LLM이 없으면 규칙 기반으로, 있으면 hybrid 방식으로 동작합니다.

## 실행

```bash
cd pocs/02-device-agent-contract
pip install -r requirements.txt
python3 device_agent_server.py
```

세션, payload, memory, recommendation을 보려면 `ui/index.html`을 열면 됩니다.

### 연결 흐름

1. 01 디바이스 시뮬레이터가 03 서버에 디바이스를 등록합니다.
2. 03 서버가 `agent.endpoint`와 `agent.command_endpoint`를 돌려줍니다.
3. 01이 02 Agent 서버의 `WS /agents/{token}`으로 연결합니다.
4. 01이 `hello`로 `device_id`, `device_type`, `registry_id`를 보냅니다.
5. 02 Agent가 03 서버에 자기 연결 정보를 다시 등록합니다.
6. 03 서버는 어떤 디바이스에 어떤 Agent가 붙었는지 저장합니다.

## 엔드포인트

- `GET /health`
- `GET /meta`
- `GET /.well-known/agent.json`
- `GET /agents`
- `GET /agents/{token}`
- `POST /agents/{token}/command`
- `WS /agents/{token}`

## 디바이스 역할

- `usv` - 수면 이동과 경로 계획
- `auv` - 수중 이동과 수심 제어
- `rov` - 정밀 탐사, 카메라, 조명 제어
