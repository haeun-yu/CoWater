# AGENTS.md

This file is the Codex harness for CoWater. Its priority is working behavior, review discipline, and documentation rules, not implementation roadmap details.

## Primary Sources

Read these first and follow them in this order:

1. `CLAUDE.md`
2. `.claude/PROCESS.md`
3. `.claude/GUIDELINES.md`
4. `.claude/DOCUMENTATION_GUIDELINES.md`

Use other `.claude/*.md` files only when the task needs domain or architecture context.

## Non-Negotiable Rules

- If anything is ambiguous, ask instead of guessing.
- For feature work: design first, side effects second, user approval third, implementation last.
- Do not silently expand scope.
- Keep changes surgical and directly related to the request.
- Do not commit or push unless the user explicitly asks.
- Do not run destructive commands such as `rm -rf`, `git reset --hard`, or `git clean -f`.

## Standard Working Process

For implementation tasks, follow this sequence:

1. Understand the request and inspect the relevant code.
2. State assumptions explicitly.
3. Present the intended design before editing.
4. List side effects:
   - directly affected files
   - indirectly affected files
   - API/schema/config/test/doc impact
5. Wait for user approval before implementing.
6. If the task is multi-step, keep an explicit plan and track progress.
7. Implement only the approved scope.
8. Verify with `git diff` and targeted tests.
9. Summarize changes, verification, and remaining risks.

If implementation reveals broader impact than expected, stop and report that before continuing.

## Coding Guidelines

Apply these rules from `.claude/GUIDELINES.md`:

- Think before coding.
- Prefer the simplest solution that satisfies the request.
- Preserve existing style and structure.
- Avoid speculative abstractions and unrequested improvements.
- Add comments only when they explain why, not what.
- Define success criteria before changing behavior.
- For bug fixes, prefer a reproduction path plus a validating test when feasible.

### Change Discipline

- Modify only files that are necessary for the request.
- Do not reformat or rename unrelated code.
- After editing, check that every changed line is still in scope.

## Documentation Rules

When the task touches docs or architecture, follow `.claude/DOCUMENTATION_GUIDELINES.md`:

- Use `docs/core/schema.md` as the single source of truth for schema and detailed structures.
- In `docs/scenarios/`, describe concepts and flow, and link to schema instead of duplicating it.
- Write diagrams in Mermaid, not as image assets.
- For architecture or behavior changes, update the relevant ADR first.
- If a new ADR is added, immediately update `docs/adr/ADR-000-index.md`.
- Keep ADR numbering sequential.
- If the user says something will be handled later, record it in the appropriate section of `docs/roadmap.md`.

## Safety and Review Triggers

Use extra caution and surface impact clearly when work touches:

- `server/system-agent/`
- registry schema or persistence shape
- agent communication protocol
- CI/CD or automation
- database schema changes

Ask before:

- adding dependencies
- making breaking API/protocol/schema changes
- changing behavior outside the approved design

## Verification Expectations

Before finishing:

- review the diff for scope control
- run the smallest relevant verification
- say explicitly what you did not verify
- call out assumptions, unresolved risks, or follow-up work

## Repo Notes

Useful references when needed:

- `.claude/COWATER_CONTEXT.md`: system context
- `docs/SYSTEM_ARCHITECTURE.md`: architecture overview
- `docs/QUICK_START.md`: manual run guidance
- `.claude/projects/-Users-teamgrit-Documents-CoWater/memory/`: project memory

Only pull in roadmap or design documents such as `.claude/SYSTEM_AGENT_DESIGN.md` or `.claude/IMPLEMENTATION_STATUS_ROADMAP.md` when the task specifically requires target-state architecture context.
