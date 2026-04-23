# 05 Control Ship Agent

This POC models the `control_ship` layer in the A2A hierarchy.

## What it does

- Accepts A2A messages over HTTP using the standard `POST /message:send` binding
- Publishes an Agent Card at `/.well-known/agent-card.json`
- Manages child agents and dispatch plans
- Relays status upstream to the control center
- Stores inbox, outbox, dispatches, and memory

## Run

```bash
cd pocs/05-control-ship-agent
pip install -r requirements.txt
python3 device_agent_server.py
```

## Key endpoints

- `GET /.well-known/agent-card.json`
- `GET /meta`
- `GET /state`
- `GET /children`
- `POST /children/register`
- `POST /message:send`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}:cancel`
- `POST /a2a/inbox`
- `POST /dispatch`

## A2A flow

- `control_center -> control_ship`: `task.assign`
- `control_ship -> control_center`: `task.accept` / `status.report`
- `control_ship -> device agents`: planned dispatch records
