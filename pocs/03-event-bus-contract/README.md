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
