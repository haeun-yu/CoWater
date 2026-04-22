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

## Run

```bash
cd pocs/04-realtime-dashboard
python3 src/server.py --port 8744
```

Open `http://127.0.0.1:8744`.

Docker:

```bash
docker compose up
```
