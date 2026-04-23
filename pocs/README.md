# CoWater PoC Workspace

This workspace replaces the old integrated CoWater shape with small, independent
proofs of concept. Each PoC must be runnable and reviewable without requiring the
whole historical stack.

## PoC Boundaries

| PoC | Purpose | Primary Output |
| --- | --- | --- |
| `01-device-streams` | Multi-stream device generation | `telemetry.*`, `sensor.*`, `device.event.*` JSONL |
| `02-device-agent-contract` | Per-device Agent hub for `usv`, `auv`, `rov` | `ws://.../agents/{token}` |
| `03-device-registration-server` | Device registration and address generation | Device metadata validation |
| `04-realtime-dashboard` | Real-time operator UI | Map/status/alert UI prototype |
| `05-control-ship-agent` | Mid-tier `control_ship` A2A hub | Child dispatch and upstream status reports |
| `06-control-center-system-agent` | Top-tier `control_center` A2A hub | Mission planning and direct routing |
| `07-mission-simulator` | End-to-end mission scenario demo | Scenario replay |
| `08-command-control` | Approval, authorization, command path | `respond.command.*` |
| `09-report-learning` | Reports and feedback loop | Incident reports and suggestions |

## Runnable Chain

The following PoCs are currently executable:

```bash
# 01: generate multi-stream device JSONL
python3 pocs/01-device-streams/src/simulator.py --ticks 3 --output pocs/_out/device-streams.jsonl

# 02: run per-device agent hub
python3 pocs/02-device-agent-contract/device_agent_server.py

# 03: register and inspect device metadata
python3 pocs/03-device-registration-server/src/device_registration_server.py

# 05: run the control ship A2A hub
python3 pocs/05-control-ship-agent/device_agent_server.py

# 06: run the control center A2A hub
python3 pocs/06-control-center-system-agent/device_agent_server.py
```

## Hierarchy Note

The active A2A hierarchy demo is `06-control-center-system-agent -> 05-control-ship-agent -> 02-device-agent-contract`.
Standalone workflow PoCs may still exist in the tree, but they are not the primary control-path demo anymore.

## Rules

- PoCs do not import implementation code from other PoCs.
- Shared contracts live in `packages/schemas`.
- Integration happens through files, HTTP, WebSocket, or an event bus.
- A PoC should state its excluded scope explicitly.
- The old `services/` stack is legacy reference material during the rebuild.
