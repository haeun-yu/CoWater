# PoC 01: Device Streams

## Goal

Prove that one maritime device can publish multiple independent streams at the
same time, and that parent-child device structure can be represented without a
central Core service.

## Scope

Included:

- Control USV, AUV, and ROV sample devices
- Position, status, sonar, task, network, and event streams
- Shared schema usage from `packages/schemas`
- JSONL output for downstream PoCs

Excluded:

- Protocol parsing
- Redis/NATS transport
- Core persistence
- UI rendering
- Detection/response agents

## Run

```bash
cd pocs/01-device-streams
python3 src/simulator.py --ticks 5 --format table
```

Use `--format jsonl` when downstream PoCs need machine-readable events.

Write a fixture:

```bash
python3 src/simulator.py --ticks 10 --output out/device-streams.jsonl
```

Run with Docker:

```bash
docker compose up
```

Docker prints the stream table to logs by default.

## Success Criteria

- Each device emits more than one stream.
- Stream subjects remain separated.
- Parent-child relationships stay in envelope metadata, not subject names.
- Output can be used by later PoCs without importing this PoC's internals.
