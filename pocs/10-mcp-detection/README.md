# PoC 10: MCP Detection Server

## Goal

Detection agents의 규칙(rule)들을 **Anthropic MCP (Model Context Protocol)** Tool로 노출하고,
Analysis 단계에서 **Claude가 tool_use로 호출**하여 rule-aware 분석을 수행합니다.

표준 MCP 프로토콜을 따르는 Production-ready 패턴을 검증합니다.

## Protocol Flow

```
[Mock Scenario]
  2척 선박 (VESSEL-001: 35.10°N 129.05°E, VESSEL-002: 35.12°N 129.07°E)
  2개 관제 구역 (금지/제한)
        ↓
[mcp-client] Claude에게 선박 현황 전달
        ↓
Claude가 필요한 도구 호출 (stop_reason == "tool_use")
        ├─ get_detection_rules("cpa")
        │   → CPA/TCPA 임계값 반환
        │       ("critical_cpa_nm": 0.5, "warning_cpa_nm": 2.0 등)
        │
        ├─ compute_cpa(VESSEL-001, VESSEL-002)
        │   → CPA: 0.3 NM, TCPA: 8.2 min, severity: "critical"
        │
        ├─ get_detection_rules("zone")
        │   → 금지/제한 구역 정책 반환
        │
        ├─ check_zone_breach(VESSEL-001, zones)
        │   → breach_count: 1, severity: "critical" (금지구역 내)
        │
        └─ check_zone_breach(VESSEL-002, zones)
            → breach_count: 0, severity: "safe"
        ↓
[mcp-server] 모든 도구 실행 결과 반환
        ↓
Claude가 tool 결과를 분석 (stop_reason == "end_turn")
        ↓
최종 리포트 출력 (한글, Markdown)
  - 긴급 상황 판정: "CRITICAL — 두 선박 충돌 위험 + VESSEL-001 금지구역 침범"
  - 권고 조치: "VESSEL-001 침로 변경 + 통신 강제"
```

## Technical Stack

### Standards
- **MCP**: Anthropic Model Context Protocol (`mcp>=1.6.0`)
- **Transport**: streamable-http (HTTP + Server-Sent Events)
- **LLM**: Claude 3.5 Haiku (`claude-haiku-4-5-20251001`)
- **API**: JSON-RPC 2.0 for tool calls

### Architecture
```
┌─────────────────────────────────────────────────────┐
│ mcp-client (Analysis Agent)                         │
│  ├─ anthropic.Anthropic() — Claude API client      │
│  └─ httpx.Client() — MCP HTTP transport            │
└──────────────────┬──────────────────────────────────┘
                   │ (tool_use JSON-RPC)
┌──────────────────▼──────────────────────────────────┐
│ mcp-server (FastMCP + streamable-http)              │
│  ├─ Tool 1: get_detection_rules()                  │
│  ├─ Tool 2: compute_cpa()                          │
│  └─ Tool 3: check_zone_breach()                    │
└─────────────────────────────────────────────────────┘
```

## Files

| 파일 | 역할 |
|------|------|
| `requirements.txt` | 의존성: mcp, anthropic, httpx |
| `src/mcp_server.py` | FastMCP 서버 (detection tools 노출) |
| `src/mcp_client.py` | Claude 클라이언트 (tool_use agentic loop) |
| `docker-compose.yml` | mcp-server + mcp-client 오케스트레이션 |

## Run

### 필수 사전 작업
```bash
# ANTHROPIC_API_KEY 발급 (https://console.anthropic.com)
export ANTHROPIC_API_KEY=sk-...
```

### Docker (권장)
```bash
cd pocs/10-mcp-detection

# 방법 1: docker compose
ANTHROPIC_API_KEY=sk-... docker compose up

# 방법 2: 배경에서 실행
ANTHROPIC_API_KEY=sk-... docker compose up -d
docker compose logs -f mcp-client
```

### Local (Python 직접)
```bash
cd pocs/10-mcp-detection

# Terminal 1: MCP 서버 시작
pip install -r requirements.txt
python src/mcp_server.py
# 출력: "Starting MCP Detection Server on 0.0.0.0:8000..."

# Terminal 2: Claude 클라이언트 실행
export ANTHROPIC_API_KEY=sk-...
export MCP_SERVER_URL=http://localhost:8000
python src/mcp_client.py
```

## Expected Output

```
2026-04-22 10:30:45 [MCP Client] INFO: Starting Claude analysis with MCP tools...
2026-04-22 10:30:45 [MCP Client] INFO: MCP Server: http://mcp-server:8000

--- Iteration 1 ---
[Tool Call] get_detection_rules
  Input: {"agent_type": "cpa"}
[Tool Result] get_detection_rules
  Output: {"agent_type": "cpa", "rules": {...}, ...}

[Tool Call] compute_cpa
  Input: {"platform_a": {...}, "platform_b": {...}}
[Tool Result] compute_cpa
  Output: {"cpa_nm": 0.3, "tcpa_min": 8.2, "severity": "critical", ...}

[Tool Call] get_detection_rules
  Input: {"agent_type": "zone"}
[Tool Result] get_detection_rules
  Output: {"agent_type": "zone", "rules": {...}, ...}

[Tool Call] check_zone_breach
  Input: {"platform": {...}, "zones": [...]}
[Tool Result] check_zone_breach
  Output: {"platform_id": "VESSEL-001", "breach_count": 1, ...}

=== Claude 최종 분석 결과 ===

## 해양관제 분석 리포트

### 🚨 긴급 상황 판정: **CRITICAL**

#### 1. 선박 간 충돌 위험
- **대상**: VESSEL-001 (화물선 A) ↔ VESSEL-002 (화물선 B)
- **CPA**: 0.3 NM (임계값: critical < 0.5 NM)
- **TCPA**: 8.2분 (임계값: critical < 10분)
- **판정**: 🔴 **긴급 — 8분 이내 충돌**

#### 2. 구역 침범
- **VESSEL-001**: 부산항 금지구역 A 내 위치
  - 거리: 0.2 NM (반경 0.5 NM)
  - 판정: 🔴 **긴급 — 즉시 격출 필요**

#### 3. 권고 조치
1. **VESSEL-001**: 침로 즉시 변경 (제안: 315°)
2. **통신**: 양 선박 모두 VHF 채널 16 (비상파)으로 강제 호출
3. **관제**: 근처 해양경찰/해군 기동 준비
...
```

## Success Criteria

✅ **Functional**
- MCP 서버가 HTTP streamable-http로 3개 도구 제공
- Claude가 도구를 순차 호출 (stop_reason == "tool_use")
- 최종 분석이 모든 도구 결과를 포함하여 생성됨

✅ **Standards Compliance**
- MCP 1.6.0+ 표준 준수 (JSON-RPC 2.0)
- Claude tool_use API 올바른 사용 (anthropic 0.49.0+)
- 음역 처리: 도구명, 파라미터명 영문, 결과물 한글

✅ **Production Readiness**
- Error handling: MCP 도구 실패 시 graceful fallback
- Logging: 모든 단계 추적 가능 (DEBUG/INFO 레벨)
- Timeout 설정: 도구 호출 최대 30초, Claude 최대 2048 tokens

## Included

- MCP fastmcp 서버 (zero-dependency math tools)
- Claude agentic loop (stop_reason polling)
- Docker 오케스트레이션 (서비스 간 healthcheck)
- Structured logging (단계별 추적)

## Excluded

- Real Detection Agent 연동 (mock scenario만 사용)
- Redis pub/sub (MCP HTTP로 완전 대체)
- Database 저장 (stdout 출력만)

## Protocol Details

### MCP Tool Definition (anthropic SDK format)

각 도구는 `anthropic.messages.create(tools=[...])` 파라미터로 정의:

```python
{
    "name": "compute_cpa",
    "description": "두 선박 간 CPA/TCPA 계산",
    "input_schema": {
        "type": "object",
        "properties": {
            "platform_a": {"type": "object", "properties": {...}},
            "platform_b": {"type": "object", "properties": {...}},
        },
        "required": ["platform_a", "platform_b"],
    },
}
```

### Agentic Loop Pattern

```python
while True:
    response = client.messages.create(
        tools=MCP_TOOLS,
        messages=messages,
    )
    
    if response.stop_reason == "tool_use":
        # 도구 호출
        for block in response.content:
            if block.type == "tool_use":
                result = call_mcp_tool(block.name, block.input, mcp_url)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                ]})
    
    elif response.stop_reason == "end_turn":
        # 최종 응답 출력
        break
```

### JSON-RPC 2.0 Tool Call

Client → Server:
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "compute_cpa",
    "arguments": {"platform_a": {...}, "platform_b": {...}}
  },
  "id": "uuid-1234"
}
```

Server → Client:
```json
{
  "jsonrpc": "2.0",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"cpa_nm\": 0.3, \"tcpa_min\": 8.2, \"severity\": \"critical\"}"
      }
    ]
  },
  "id": "uuid-1234"
}
```

## References

- [MCP Specification](https://modelcontextprotocol.io/)
- [Anthropic SDK - Tool Use](https://docs.anthropic.com/en/docs/build-a-system-prompt-with-tools)
- [Detection Agent Rules](../../services/detection-agents/config.py)
