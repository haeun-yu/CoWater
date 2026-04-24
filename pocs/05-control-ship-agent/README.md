# 05 Regional Orchestrator Agent

This POC models the `regional_orchestrator` layer in the A2A hierarchy.

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
- `GET /manifest`
- `GET /meta`
- `GET /state`
- `GET /children`
- `POST /agents/register`
- `POST /children/register`
- `POST /message:send`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}:cancel`
- `POST /a2a/inbox`
- `POST /dispatch`

## A2A flow

- `system_center -> regional_orchestrator`: `task.assign`
- `regional_orchestrator -> system_center`: `task.accept` / `status.report`
- `regional_orchestrator -> device agents`: planned dispatch records
