# 06 Control Center System Agent

This PoC models the top-level `control_center` agent in the A2A hierarchy.

## What it does

- Accepts HTTP-based A2A messages
- Manages missions and child agent registrations
- Stores inbox, outbox, dispatches, and memory
- Can dispatch tasks directly to child agents when direct routing is allowed

## Run

```bash
cd pocs/06-control-center-system-agent
pip install -r requirements.txt
python3 device_agent_server.py
```

## Key endpoints

- `GET /meta`
- `GET /state`
- `GET /children`
- `GET /missions`
- `POST /children/register`
- `POST /missions`
- `POST /missions/{mission_id}/assign`
- `POST /a2a/inbox`
- `POST /dispatch`

## A2A flow

- `control_center -> control_ship`: `task.assign`
- `control_center -> device agents`: direct dispatch when allowed
- `control_ship -> control_center`: `status.report`
