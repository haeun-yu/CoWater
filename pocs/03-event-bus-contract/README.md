# PoC 03: Event Bus Contract

## Goal

Validate subject naming, QoS policy, and latest-vs-durable behavior before
choosing a long-term transport.

## Scope

Included:

- Subject taxonomy
- Stream policy file
- Redis and NATS implementation candidates
- Contract tests

Excluded:

- Device protocol parsing
- UI
- Long-term storage

## Success Criteria

- `telemetry.*` and `sensor.*` streams remain separate from `detect.*` events.
- `latest` streams can replace old values by device.
- `durable` events can be replayed.
- Consumers subscribe only to the subjects they need.

## Run

Generate stream fixtures from PoC 01 and replay them through the contract bus:

```bash
python3 ../01-device-streams/src/simulator.py --ticks 3 --output out/device-streams.jsonl
python3 src/bus_contract.py --input out/device-streams.jsonl --format table
```

Use `--format json` when another process needs the raw contract summary.

Run with Docker:

```bash
docker compose up
```

Docker prints the stream policy table to logs by default.

Expected behavior:

- `telemetry.position` appears in `latest_keys`
- `telemetry.status`, `telemetry.network`, `telemetry.task`, and `sensor.sonar`
  are counted as non-durable traffic
