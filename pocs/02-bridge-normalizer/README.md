# PoC 02: Bridge Normalizer

## Goal

Convert raw protocol payloads into the shared `DeviceStreamMessage` contract.

## Scope

Included:

- Adapter boundary for NMEA, MAVLink, ROS JSON, and custom JSON
- Raw input fixtures
- Normalized stream output fixtures

Excluded:

- Real device connections
- Event bus transport
- Detection agents
- UI

## Input

```text
raw protocol payload
```

## Output

```text
DeviceStreamMessage JSON
```

## Run

Normalize ROS NavSat JSON:

```bash
cd pocs/02-bridge-normalizer
python3 src/normalizer.py --protocol ros-navsat --input sample-data/raw-ros-navsat.json --format summary
```

Normalize decoded AIS fixture:

```bash
python3 src/normalizer.py --protocol nmea-ais --input sample-data/decoded-ais.json --format summary
```

Use `--format jsonl` when downstream PoCs need machine-readable events.

Run with Docker:

```bash
docker compose up
```

Docker prints the bridge normalization summary to logs by default.

## Success Criteria

- Every adapter returns the same shared schema shape.
- Unsupported protocol payloads fail explicitly.
- One raw payload may produce multiple stream messages.
