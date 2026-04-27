# PoC 11: A2A Inter-Agent Protocol

## 목표

Learning Agent가 Detection Agent에게 rule update 제안을 Google A2A(Agent-to-Agent) 표준으로 전송하는 에이전트 간 통신 패턴을 검증합니다.

## 프로토콜 흐름

```text
Learning Agent
  -> Detection Agent Card 조회
  -> suggest_rule_update skill 확인
  -> /tasks/send 로 rule update task 전송
  -> Detection Agent가 confidence 기준으로 즉시 적용 또는 보류
  -> 결과 artifact 반환
  -> Learning Agent가 applied/pending 변경사항 확인
```

## 기술 스택

- Google A2A Protocol
- HTTP REST
- JSON
- Agent Card discovery: `/.well-known/agent.json`

## 파일

| 파일 | 역할 |
| --- | --- |
| `requirements.txt` | FastAPI, uvicorn, httpx, pydantic 의존성 |
| `src/detection_agent_server.py` | A2A server, Agent Card, task 처리 |
| `src/learning_agent_client.py` | A2A client, task 전송과 결과 파싱 |
| `docker-compose.yml` | detection-agent + learning-agent 실행 |

## 실행

Docker:

```bash
cd pocs/11-a2a-interagent
docker compose up
```

로컬:

```bash
cd pocs/11-a2a-interagent
pip install -r requirements.txt
python src/detection_agent_server.py

# 다른 터미널
export DETECTION_AGENT_URL=http://localhost:8001
python src/learning_agent_client.py
```

## 성공 기준

- Detection Agent가 Agent Card를 제공합니다.
- Learning Agent가 skill을 발견하고 task를 전송합니다.
- confidence가 높은 제안은 즉시 적용됩니다.
- confidence가 낮은 제안은 pending으로 보류됩니다.
- 결과 artifact에서 applied/pending/current config를 확인할 수 있습니다.

## 제외 범위

- 실제 학습 데이터 연동
- 운영용 인증/권한
- 장기 저장소
