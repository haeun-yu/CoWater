# 02 Device Agent Contract

This POC provides a per-device Agent hub for `usv`, `auv`, and `rov`.
Each device type has its own Agent class: `USVAgent`, `AUVAgent`, and `ROVAgent`.
Agents can be static rule-based sessions or dynamic reasoning-based sessions.
LLM usage is optional, not required.

## What it does

- Accepts device WebSocket connections at `ws://<host>:<port>/agents/{token}`
- Ingests the same stream envelope/payload format used by POC 01
- Uses the registration `token` as the Agent session identity
- Expects an initial `hello` message with device identity before stream data
- After `hello`, re-registers Agent connection info back to the 03 registry server
- Produces simple recommendations for each device type
- Exposes per-device agent state through REST
- Supports both static and dynamic agent modes
- Works without an LLM by using rule-based planning only

## Quick start

```bash
cd pocs/02-device-agent-contract
pip install -r requirements.txt
python3 device_agent_server.py
```

Open the dashboard at `ui/index.html` to inspect sessions, payloads, memory, and recommendations.

### Connection Flow

1. POC 01 registers devices with the 03 registry server.
2. The 03 server returns `agent.endpoint` and `agent.command_endpoint`.
3. POC 01 connects to the 02 Agent server at `WS /agents/{token}`.
4. POC 01 sends `hello` with `device_id`, `device_type`, `registry_id`, and `agent_mode`.
5. The 02 Agent re-registers its connection info back to the 03 registry server.
6. The 03 server stores which Agent is attached to which device.

## Endpoints

- `GET /health`
- `GET /meta`
- `GET /.well-known/agent.json`
- `GET /agents`
- `GET /agents/{token}`
- `POST /agents/{token}/command`
- `WS /agents/{token}`

## Device roles

- `usv` - surface navigation and route planning
- `auv` - subsurface navigation and depth control
- `rov` - inspection, camera, and lighting control

## Agent modes

- `static` - fixed rule-based agent behavior
- `dynamic` - adaptive agent behavior using planner/context updates
- `llm_optional` - the planner can run without any LLM dependency
