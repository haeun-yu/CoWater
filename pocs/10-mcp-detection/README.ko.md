# PoC 10: MCP Detection Server

## 목표

Detection Agent의 rule을 Anthropic MCP(Model Context Protocol) tool로 노출하고, Analysis 단계에서 Claude가 `tool_use`로 호출해 rule-aware 분석을 수행하는 패턴을 검증합니다.

## 프로토콜 흐름

```text
Mock Scenario
  -> MCP Client가 Claude에게 선박 상황 전달
  -> Claude가 필요한 tool 호출
     - get_detection_rules
     - compute_cpa
     - check_zone_breach
  -> MCP Server가 tool 결과 반환
  -> Claude가 최종 분석 리포트 생성
```

## 기술 스택

- MCP 1.6.0+
- streamable-http
- Claude tool_use
- JSON-RPC 2.0 tool call

## 파일

| 파일 | 역할 |
| --- | --- |
| `requirements.txt` | MCP, Anthropic, HTTP client 의존성 |
| `src/mcp_server.py` | Detection tool을 제공하는 FastMCP 서버 |
| `src/mcp_client.py` | Claude tool_use loop 클라이언트 |
| `docker-compose.yml` | MCP server/client 실행 |

## 실행

사전 준비:

```bash
export ANTHROPIC_API_KEY=sk-...
```

Docker:

```bash
cd pocs/10-mcp-detection
ANTHROPIC_API_KEY=sk-... docker compose up
```

로컬:

```bash
cd pocs/10-mcp-detection
pip install -r requirements.txt
python src/mcp_server.py

# 다른 터미널
export ANTHROPIC_API_KEY=sk-...
export MCP_SERVER_URL=http://localhost:8000
python src/mcp_client.py
```

## 성공 기준

- MCP 서버가 detection tool을 HTTP streamable-http로 제공합니다.
- Claude가 `tool_use`를 통해 도구를 순차 호출합니다.
- 최종 분석 결과가 모든 tool 결과를 반영합니다.
- 도구 실패 시 graceful fallback이 가능합니다.
- 단계별 로그로 분석 흐름을 추적할 수 있습니다.

## 제외 범위

- 실제 Detection Agent 연동
- Redis pub/sub
- DB 저장
