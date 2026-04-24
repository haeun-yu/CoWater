# 02 Device Agent Contract

This POC provides a per-device Agent hub for `usv`, `auv`, and `rov`.
Each device type has its own Agent class: `USVAgent`, `AUVAgent`, and `ROVAgent`.
Agents use rule-based planning when no LLM is configured, and hybrid planning when an LLM is configured.

## What it does

- Accepts device WebSocket connections at `ws://<host>:<port>/agents/{token}`
- Ingests the same stream envelope/payload format used by POC 01
- Uses the registration `token` as the Agent session identity
- Expects an initial `hello` message with device identity before stream data
- After `hello`, re-registers Agent connection info back to the 03 registry server
- Routes telemetry through a Decision Layer before execution
- Produces simple recommendations for each device type
- Exposes per-device agent state through REST
- Stores the device's allowed actions in session state and renders button-only commands in the dashboard
- Shows whether LLM is enabled for the session in the dashboard
- Uses hybrid planning when an LLM configuration exists, otherwise rule-based planning only

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
4. POC 01 sends `hello` with `device_id`, `device_type`, and `registry_id`.
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
