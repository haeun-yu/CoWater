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

## Success Criteria

- Every adapter returns the same shared schema shape.
- Unsupported protocol payloads fail explicitly.
- One raw payload may produce multiple stream messages.
