# PoC 09: Report Learning

## Goal

Summarize mission events and capture feedback for future threshold tuning.

## Scope

Included:

- Incident report from event JSONL
- Mission summary
- False-positive feedback fixture
- Threshold suggestion fixture

Excluded:

- Production LLM integration
- Automatic parameter deployment
- Persistent report database

## Success Criteria

- A mission event log can produce a readable summary.
- User feedback can be linked to an alert or flow.
- Suggested parameter changes remain pending until approved.

## Run

```bash
cd pocs/09-report-learning
python3 src/report.py --events sample-data/events.jsonl --feedback sample-data/feedback.json
```

The output contains a mission summary and a pending learning suggestion.
