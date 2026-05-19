# AGENTS.md

이 문서는 CoWater에서 Codex가 따라야 할 작업 규칙입니다. 구현 로드맵보다 작업 방식, 리뷰 규율, 문서 관리 규칙을 우선합니다.

## 우선 참고 문서

다음 순서로 먼저 읽고 따릅니다.

1. `CLAUDE.md`
2. `.claude/PROCESS.md`
3. `.claude/GUIDELINES.md`
4. `.claude/DOCUMENTATION_GUIDELINES.md`

다른 `.claude/*.md` 파일은 작업에 도메인이나 아키텍처 맥락이 필요할 때만 참고합니다.

## 필수 규칙

- 애매한 점이 있으면 추측하지 말고 질문합니다.
- 기능 작업은 반드시 설계, 사이드 이펙트, 사용자 승인, 구현 순서로 진행합니다.
- 범위를 조용히 늘리지 않습니다.
- 변경은 요청과 직접 관련된 범위로만 최소화합니다.
- 사용자가 명시적으로 요청하지 않으면 커밋하거나 푸시하지 않습니다.
- `rm -rf`, `git reset --hard`, `git clean -f` 같은 파괴적 명령은 실행하지 않습니다.

## 표준 작업 절차

구현 작업은 다음 순서를 따릅니다.

1. Understand the request and inspect the relevant code.
2. State assumptions explicitly.
3. Present the intended design before editing.
4. 사이드 이펙트를 정리합니다.
   - 직접 영향 파일
   - 간접 영향 파일
   - API, 스키마, 설정, 테스트, 문서 영향
5. Wait for user approval before implementing.
6. If the task is multi-step, keep an explicit plan and track progress.
7. Implement only the approved scope.
8. Verify with `git diff` and targeted tests.
9. Summarize changes, verification, and remaining risks.

구현 중 영향 범위가 예상보다 커지면 계속 진행하지 말고 먼저 보고합니다.

## 코딩 가이드라인

`.claude/GUIDELINES.md`의 다음 규칙을 적용합니다.

- Think before coding.
- Prefer the simplest solution that satisfies the request.
- Preserve existing style and structure.
- Avoid speculative abstractions and unrequested improvements.
- Add comments only when they explain why, not what.
- Define success criteria before changing behavior.
- For bug fixes, prefer a reproduction path plus a validating test when feasible.

### 변경 범위 관리

- Modify only files that are necessary for the request.
- Do not reformat or rename unrelated code.
- After editing, check that every changed line is still in scope.

## 문서 관리 규칙

문서나 아키텍처를 다룰 때는 `.claude/DOCUMENTATION_GUIDELINES.md`를 따릅니다.

- 스키마와 상세 구조는 `docs/core/schema.md`를 단일 정본으로 사용합니다.
- `docs/scenarios/`에는 구조를 복제하지 말고 개념과 흐름만 적고 스키마를 링크합니다.
- 다이어그램은 이미지 대신 Mermaid로 작성합니다.
- 아키텍처나 동작을 바꾸면 관련 ADR을 먼저 갱신합니다.
- 새 ADR을 추가하면 즉시 `docs/adr/ADR-000-index.md`도 갱신합니다.
- ADR 번호는 순차적으로 유지합니다.
- 사용자가 나중에 처리하겠다고 한 내용은 `docs/roadmap.md`의 적절한 섹션에 남깁니다.

## 주의가 필요한 변경

다음 범위를 건드릴 때는 영향 범위를 더 명확히 드러내고 신중하게 진행합니다.

- `server/system-agent/`
- registry schema or persistence shape
- agent communication protocol
- CI/CD or automation
- database schema changes

다음 변경은 먼저 확인을 받습니다.

- 의존성 추가
- 호환성을 깨는 API, 프로토콜, 스키마 변경
- 승인된 설계 범위를 벗어나는 동작 변경

## 검증 기준

마무리 전에 다음을 확인합니다.

- `git diff`로 범위가 통제됐는지 확인합니다.
- 가장 작은 관련 검증을 실행합니다.
- 무엇을 검증하지 못했는지 명시합니다.
- 가정, 미해결 위험, 후속 작업을 분명히 적습니다.

## 저장소 메모

필요할 때 참고할 만한 경로입니다.

- `.claude/COWATER_CONTEXT.md`: 시스템 빠른 참고 문서
- `docs/SYSTEM_ARCHITECTURE.md`: 아키텍처 개요
- `docs/QUICK_START.md`: 수동 실행 가이드
- `.claude/projects/-Users-teamgrit-Documents-CoWater/memory/`: 프로젝트 메모리

`.claude/SYSTEM_AGENT_DESIGN.md`, `.claude/IMPLEMENTATION_STATUS_ROADMAP.md` 같은 로드맵이나 설계 문서는 목표 아키텍처 맥락이 꼭 필요할 때만 참고합니다.

## 도메인 문서 참조 규칙

CoWater는 도메인 언어와 아키텍처 결정을 한 곳에서 추적하는 단일 컨텍스트 구성을 사용합니다.

- `CONTEXT.md`: 도메인 언어, 핵심 개념, 아키텍처 용어
- `docs/adr/`: 주요 설계 결정을 담은 ADR 모음
- `.claude/COWATER_CONTEXT.md`: 빠르게 훑는 시스템 참고 문서

다음 상황이 생기면 문서를 이렇게 갱신합니다.

- 새 개념이나 용어를 추가할 때 → `CONTEXT.md` 갱신
- 아키텍처 결정을 내릴 때 → `docs/adr/`에 ADR 추가 후 `docs/adr/ADR-000-index.md` 갱신
- 용어 충돌을 발견했을 때 → `CONTEXT.md`와 관련 ADR을 함께 갱신

`improve-codebase-architecture`, `diagnose`, `tdd` 같은 스킬은 이 문서들을 기준으로 도메인 제약과 용어를 해석합니다.

## 이슈 추적과 트리아지 규칙

CoWater의 이슈는 GitHub Issues에서 관리합니다.

이슈 작업은 `gh` CLI를 사용합니다.

```bash
gh issue create --title "..." --body "..."
gh issue view <number>
gh issue list --label needs-triage
gh issue edit <number> --add-label needs-triage
gh issue edit <number> --remove-label needs-info
```

표준 트리아지 라벨은 아래 다섯 개입니다.

| 라벨 | 의미 | 다음 단계 |
|-------|---------|----------|
| `needs-triage` | 관리자의 1차 검토가 필요함 | → `needs-info` 또는 `ready-for-agent` |
| `needs-info` | 제보자의 추가 설명을 기다림 | → `needs-triage` 또는 `ready-for-agent` |
| `ready-for-agent` | 사양이 충분해 에이전트가 작업 가능함 | → 필요 시 `ready-for-human` |
| `ready-for-human` | 사람이 직접 구현해야 함 | 종료 상태 |
| `wontfix` | 처리하지 않기로 결정함 | 종료 상태 |

`triage`는 이 라벨을 기준으로 이슈를 이동하고, `to-issues`는 계획을 이슈 단위로 나누며, `to-prd`는 PRD를 이슈로 게시합니다.

## 임시 사용자 규칙 업데이트

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
