# PoC 05: Detection Agents

## Goal

Turn telemetry and sensor streams into domain detection events.

## Scope

Included:

- Mine detection from sonar contacts
- Network degradation detection
- Simple anomaly detection from position/status
- Agent-local cooldown and dedup

Excluded:

- LLM analysis
- Alert creation
- UI

## Input

```text
telemetry.*
sensor.*
```

## Output

```text
detect.mine.{deviceId}
detect.network.{deviceId}
detect.anomaly.{deviceId}
```

## Success Criteria

- Agents subscribe only to relevant streams.
- Detection events carry `flow_id` and `causation_id` where applicable.
- Duplicate detection is suppressed within a configurable cooldown window.

## Run

```bash
cd pocs/05-detection-agents
python3 src/detect.py --input sample-events/sonar-contact.json --threshold 0.4 --format table
```

The output shows a readable detection table. Use `--format jsonl` when
downstream PoCs need the `detect.mine.{deviceId}` domain event.

Run with Docker:

```bash
docker compose up
```
