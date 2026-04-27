# 06 System Center Agent

This PoC models the system-level `system_center` agent that watches the fleet, analyzes incidents, and coordinates remediation.

## What it does

- Accepts A2A messages over HTTP using the standard `POST /message:send` binding
- Accepts raw system events over `POST /events/ingest`
- Publishes an Agent Card at `/.well-known/agent-card.json`
- Syncs child manifests from the device registry at `03`
- Creates alerts for meaningful system events and tracks response status
- Routes remediation through the `regional_orchestrator` when available, or directly to device agents through their command endpoints when needed
- Stores inbox, outbox, dispatches, events, and memory locally, while publishing alerts/responses to the 03 registry as the canonical record

## Structure

```text
src/
├─ app.py
├─ core/
│  ├─ analysis.py
│  ├─ alerts.py
│  ├─ config.py
│  ├─ responses.py
│  ├─ routing.py
│  ├─ state.py
│  └─ models.py
├─ events/
│  ├─ ingest.py
│  └─ models.py
├─ registry/
│  ├─ child_registry.py
│  └─ manifest.py
├─ transport/
│  ├─ a2a.py
│  └─ http.py
└─ __init__.py
```

`app.py` keeps the FastAPI routing layer, while `core/` holds analysis/state/routing helpers, `events/` holds ingress models and ingestion logic, `registry/` holds manifest and child registry helpers, and `transport/` holds reusable HTTP dispatch helpers.

## UI pages

- `ui/index.html`: dashboard
- `ui/events.html`: event ingestion and live event/inbox/outbox view
- `ui/alerts.html`: alert ledger and acknowledgement
- `ui/responses.html`: response ledger and dispatch records

## Run

```bash
cd pocs/06-control-center-system-agent
pip install -r requirements.txt
python3 device_agent_server.py
```

## Key endpoints

- `GET /.well-known/agent-card.json`
- `GET /manifest`
- `GET /meta`
- `GET /state`
- `GET /registry`
- `GET /children`
- `GET /missions`
- `POST /agents/register`
- `POST /children/register`
- `POST /message:send`
- `POST /events/ingest`
- `POST /events/ingest/a2a`
- `GET /events`
- `GET /alerts`
- `GET /responses`
- `POST /registry/sync`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}:cancel`
- `POST /missions`
- `POST /missions/{mission_id}/assign`
- `POST /a2a/inbox`
- `POST /dispatch`
- `POST /alerts/{alert_id}/ack`

## A2A flow

- `system event -> analysis -> alert -> response`
- `system_center -> regional_orchestrator`: `task.assign`
- `system_center -> device agents`: direct command dispatch when the route allows it
- `regional_orchestrator -> system_center`: `status.report`
