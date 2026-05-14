# Issue Tracker: GitHub Issues

Issues for CoWater live in [GitHub Issues](https://github.com/haeun-yu/CoWater/issues).

## Skill Integration

The following skills read from and write to GitHub Issues:

- `triage` — moves issues through the triage workflow
- `to-issues` — breaks plans into issues
- `to-prd` — publishes PRDs as issues
- `review` — links PRs to issues

## Workflow

Use the `gh` CLI to interact with issues:

```bash
gh issue create --title "..." --body "..."
gh issue view <number>
gh issue list --label needs-triage
```

See [`docs/agents/triage-labels.md`](triage-labels.md) for the label vocabulary.
