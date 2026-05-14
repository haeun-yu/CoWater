# Domain Documentation

CoWater uses a single-context layout for domain language and architecture decisions.

## Files to consult

- **`CONTEXT.md`** — Domain language, key concepts, architecture vocabulary
- **`docs/adr/`** — Architecture Decision Records for major design choices
- **`.claude/COWATER_CONTEXT.md`** — System context (quick reference)

## Skill Integration

These skills read domain docs when analyzing code or planning work:

- `improve-codebase-architecture` — consults `CONTEXT.md` + `docs/adr/` to understand domain constraints
- `diagnose` — uses domain language to frame root-cause hypotheses
- `tdd` — aligns test names and assertions with domain terminology

## Updating Domain Docs

When you:

- **Add a new concept or term** → update `CONTEXT.md`
- **Make an architectural decision** → add an ADR to `docs/adr/`, then update `docs/adr/ADR-000-index.md`
- **Find terminology conflicts** → update `CONTEXT.md` and relevant ADRs together

See `AGENTS.md` for documentation rules.
