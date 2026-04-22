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

## Runnable Chain

The following PoCs are currently executable:

```bash
# 01: generate multi-stream device JSONL
python3 pocs/01-device-streams/src/simulator.py --ticks 3 --output pocs/_out/device-streams.jsonl

# 02: normalize raw protocol fixture
python3 pocs/02-bridge-normalizer/src/normalizer.py --protocol ros-navsat --input pocs/02-bridge-normalizer/sample-data/raw-ros-navsat.json

# 03: replay stream JSONL through contract bus
python3 pocs/03-event-bus-contract/src/bus_contract.py --input pocs/_out/device-streams.jsonl

# 05: detect mine-like sonar contacts
python3 pocs/05-detection-agents/src/detect.py --input pocs/_out/device-streams.jsonl --threshold 0.4 > pocs/_out/detect-events.jsonl

# 06: turn detect.mine into analysis and alert candidates
python3 pocs/06-agent-workflow/src/workflow.py --input pocs/_out/detect-events.jsonl
```

## Rules

- PoCs do not import implementation code from other PoCs.
- Shared contracts live in `packages/schemas`.
- Integration happens through files, HTTP, WebSocket, or an event bus.
- A PoC should state its excluded scope explicitly.
- The old `services/` stack is legacy reference material during the rebuild.
