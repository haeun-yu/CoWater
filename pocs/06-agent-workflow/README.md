# PoC 06: Agent Workflow

## Goal

Validate the event chain from detection to analysis to response.

## Scope

Included:

- `detect.* -> analyze.* -> respond.*`
- `flow_id` propagation
- `causation_id` chain
- Alert and command candidates

Excluded:

- Device input
- Full dashboard
- Long-term reporting

## Success Criteria

- A sample `detect.mine` event produces an analysis result.
- Response can create an alert or command recommendation.
- The whole event chain is traceable by `flow_id`.

## Run

```bash
cd pocs/06-agent-workflow
python3 src/workflow.py --input sample-events/detect-mine.json
```

The output is JSONL containing:

- an `analyze.mine` agent event
- a `mine_detected` alert candidate
