# Triage Labels

CoWater uses five canonical triage labels:

| Label | Meaning | Workflow |
|-------|---------|----------|
| `needs-triage` | Maintainer needs to evaluate | → `needs-info` or `ready-for-agent` |
| `needs-info` | Waiting on reporter to clarify | → `needs-triage` or `ready-for-agent` |
| `ready-for-agent` | Fully specified, AFK-ready | → `ready-for-human` (if blocked) |
| `ready-for-human` | Needs human implementation | Terminal state |
| `wontfix` | Will not be actioned | Terminal state |

## Usage

Apply labels via `gh issue edit`:

```bash
gh issue edit <number> --add-label needs-triage
gh issue edit <number> --remove-label needs-info
```

## Rationale

These labels let the `triage` skill automate issue routing without needing custom integrations.
