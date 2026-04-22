# CoWater PoC Workspace

This workspace replaces the old integrated CoWater shape with small, independent
proofs of concept. Each PoC must be runnable and reviewable without requiring the
whole historical stack.

## PoC Boundaries

| PoC | Purpose | Primary Output |
| --- | --- | --- |
| `01-device-streams` | Multi-stream device generation | `telemetry.*`, `sensor.*`, `device.event.*` JSONL |
| `02-bridge-normalizer` | Raw protocol to normalized stream conversion | `DeviceStreamMessage` |
| `03-event-bus-contract` | Subject, QoS, latest/durable behavior | Stream policy validation |
| `04-realtime-dashboard` | Real-time operator UI | Map/status/alert UI prototype |
| `05-detection-agents` | Stream to domain detection events | `detect.*` |
| `06-agent-workflow` | `detect -> analyze -> respond` chain | Alerts and commands |
| `07-mission-simulator` | End-to-end mission scenario demo | Scenario replay |
| `08-command-control` | Approval, authorization, command path | `respond.command.*` |
| `09-report-learning` | Reports and feedback loop | Incident reports and suggestions |

## Rules

- PoCs do not import implementation code from other PoCs.
- Shared contracts live in `packages/schemas`.
- Integration happens through files, HTTP, WebSocket, or an event bus.
- A PoC should state its excluded scope explicitly.
- The old `services/` stack is legacy reference material during the rebuild.
