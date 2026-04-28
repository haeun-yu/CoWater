# CoWater PoC Workspace

This workspace now models the layered unmanned-vehicle Agent system as PoCs 1-6. `00-device-registration-server` is shared infrastructure: lower and middle Agents register their local device metadata at startup and receive an id/token.

## Boundaries

| PoC | Purpose | Runtime Unit |
| --- | --- | --- |
| `00-device-registration-server` | Device id/name/token/agent endpoint registry | Shared API server |
| `01-usv-lower-agent` | USV simulator + lower execution Agent | One process per USV |
| `02-auv-lower-agent` | AUV simulator + lower execution Agent | One process per AUV |
| `03-rov-lower-agent` | ROV simulator + lower execution Agent | One process per ROV |
| `04-usv-middle-agent` | Relay/coordination USV simulator + middle Agent | One process per relay USV |
| `05-control-ship-middle-agent` | Control Ship simulator + middle Agent | One process per control ship |
| `06-system-supervisor-agent` | Upper System Supervisor Agent | One system supervisor process |

Older PoCs such as `01-device-streams`, `02-device-agent-contract`, `05-control-ship-agent`, and `06-control-center-system-agent` remain as reference implementations.

## Run

Start the shared registry first:

```bash
python3 pocs/00-device-registration-server/device_registration_server.py --host 127.0.0.1 --port 8003
```

Run Agents from separate terminals. Running the same PoC twice creates two device instances unless you pin `COWATER_INSTANCE_ID`.

```bash
python3 pocs/01-usv-lower-agent/device_agent.py --port 9111
python3 pocs/01-usv-lower-agent/device_agent.py --port 9112
python3 pocs/02-auv-lower-agent/device_agent.py --port 9121
python3 pocs/03-rov-lower-agent/device_agent.py --port 9131
python3 pocs/04-usv-middle-agent/device_agent.py --port 9141
python3 pocs/05-control-ship-middle-agent/device_agent.py --port 9151
python3 pocs/06-system-supervisor-agent/system_agent.py --port 9161
```

## Communication

- MCP: reserved for System Supervisor Agent to API server integration. This pass declares the `mcp_api_client` tool in the supervisor manifest; turning the API server into an MCP server is a follow-up.
- A2A: Agent-to-Agent event/task communication. The new runtime accepts JSON-RPC `message/send` at `/` and keeps `/message:send` for compatibility with existing PoCs.
- Moth: real-time data stream boundary. Each PoC simulator produces telemetry state and track manifests; the previous direct Moth publisher remains in `01-device-streams` as reference code.

## Local Structure

Each PoC is intentionally self-contained. Shared implementation code is not imported from another PoC.

```text
agent/       decision loop, manifest, runtime state
controller/  HTTP, A2A, and command endpoints
simulator/   device state, motion, sensors, telemetry
skills/      capability catalog used by the Agent
tools/       executable helpers used by skills/agent/controller
transport/   registry and external protocol clients
storage/     local id/token persistence
```
