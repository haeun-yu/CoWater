# PoC 04: Realtime Dashboard

## Goal

Build a small operator UI that can visualize devices, streams, and alerts without
depending on the old frontend.

## Scope

Included:

- Mock API
- WebSocket feed
- Device list
- Map placeholder
- Stream status panel
- Alert panel

Excluded:

- Full CoWater UI migration
- Authentication
- Production map layers

## Success Criteria

- A mock stream feed updates the UI in real time.
- Position, status, network, task, and alert views are visually separate.
- The UI can run with fixtures from `01-device-streams`.
