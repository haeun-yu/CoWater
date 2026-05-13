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

## Temporary User Rules Update

- docs 기준으로 구현한다.
- 사용자가 `docs` 전체를 기준으로 구현하라고 하면, 구현 전에 `docs/` 디렉토리의 모든 문서를 확인한 뒤 구현 순서를 정한다.
- `docs` 전체 확인이 끝나기 전에는 전체 구현이 끝난 것처럼 보고하지 않는다.
- 구현은 기존 코드 호환성보다 docs를 우선한다.
- docs에 맞지 않으면 기존 구현을 유지하려고 하지 않는다.
- docs에 없는 결정은 혼자 판단하지 않는다.
- 구현 중 docs에 없는 내용이 나오면 임의로 정하지 않는다.
- 반드시 사용자 검토를 받아야 한다.
- 문서 충돌은 USER_CHECK.md에 기록한다.
- docs끼리 모순되거나 맞지 않으면 USER_CHECK.md에 적는다.
- 그때는 추천안으로 임시 구현은 진행할 수 있다.
- 나중에 USER_CHECK.md를 보고 최종 결정을 내린다.
- 구현은 끝까지 진행하고, 중간보고로 멈추지 않는다.
- 정말 중요한 확인 사안이 아니면 중간에 멈추지 말고 끝까지 진행한다.
- 다 끝낸 뒤에 보고한다.
- 사용자가 중간보고 없이 끝까지 진행하라고 하면, 진행 상황 공유 때문에 작업을 멈추거나 부분 완료 상태로 보고하지 않는다.
- 최종 보고 전에는 `docs`와 구현의 불일치를 최소 한 번 이상 다시 대조 검토한다.
- 최종 보고는 `docs` 전체 확인 여부, 구현 완료 범위, 남아 있는 불일치 유무를 명시한 뒤에만 한다.
- USER_CHECK.md는 불필요한 내용 없이 정리한다.
- 해결된 충돌 메모나 호환성 유지 같은 문구는 남기지 않는다.
- 최종 결정만 남긴다.
- 문서에 없는 추가 구현이 있는지 항상 점검한다.
- 추가한 내용 중 문서 근거가 약한 게 있으면 먼저 밝힌다.
- 승인하지 않은 확장은 하지 않는다.
- 최종 목표는 docs와 구현이 맞을 때까지 반복 검토하는 것이다.
- 한 번 수정하고 끝내는 게 아니라, docs 기준에 맞을 때까지 검토, 재구현, 수정 반복한다.
- `docs` 기준 구현 요청에서는 상태값, 이벤트 타입, 역할명, 생명주기처럼 문서 전역에 걸친 표준을 부분 수정으로 끝내지 않고, 관련 구현 전체에 남은 불일치를 반복 검토한다.
