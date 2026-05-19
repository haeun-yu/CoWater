# CoWater Claude 작업 안내

> **최우선 규칙들** (매 작업 전 30초 안에 읽기)

---

## 🔴 핵심 규칙

### 1️⃣ 의심되면 반드시 물어보기

- 애매한 부분 있으면 → **물어보기**
- 이상하다고 느껴지면 → **물어보기**
- "음..." 하는 느낌 들면 → **물어보기**
- **절대** 추측하고 진행하지 말기

### 2️⃣ 기능 구현: 설계 → 승인 → 구현

```
사용자 요청
  ↓
설계 제시 (어떻게 만들지)
  ↓
사이드 이펙트 분석 (뭐가 영향받을지)
  ↓
사용자 승인 (GO 신호)
  ↓
구현 (승인된 범위 내에서만)
```

### 3️⃣ 권한 제약 (자동)

- ❌ `git commit` - 사용자 승인 필수
- ❌ `git push` - 사용자 승인 필수
- ❌ `rm -rf`, 위험한 삭제 - 차단됨
- ✅ `Read`, `Edit` - 자유
- ✅ `git status`, `git diff` - 자유

### 4️⃣ Git Hook (자동 검증)

- **pre-commit**: debug code, secrets, .env 파일 감지
- **pre-push**: 브랜치 보호, 문서화, 메모리 확인

---

## 📚 상세 안내

| 내용                                             | 위치                                  | 읽는 시간 |
| ------------------------------------------------ | ------------------------------------- | --------- |
| **프로세스** (설계, 리뷰, 구현 단계별)           | `.claude/PROCESS.md`                  | 5분       |
| **CoWater 컨텍스트** (아키텍처, 에이전트, 용어)  | `.claude/COWATER_CONTEXT.md`          | 5분       |
| **일반 가이드라인** (코딩 방식, 베스트 프랙티스) | `.claude/GUIDELINES.md`               | 3분       |
| **문서 관리 규칙** (중복 배제, Mermaid, ADR)     | `.claude/DOCUMENTATION_GUIDELINES.md` | 2분       |

---

## ✅ 매 작업 시작 전 체크리스트

- [ ] **이 CLAUDE.md** 읽음 (30초)
- [ ] 요청이 **명확한가?** 아니면 물어보기
- [ ] **기능이라면** → `.claude/PROCESS.md` 참고
- [ ] **불명확한 부분 있나?** → 물어보기
- [ ] **설계 제시** → 사용자 승인 대기
- [ ] **구현 후** → git hooks 자동 검증

---

## 🚨 가장 많이 하는 실수들

| 실수                 | 해결책                     |
| -------------------- | -------------------------- |
| 추측으로 구현        | 설계 제시 후 승인받기      |
| 사이드 이펙트 무시   | 영향받는 모든 파일 검토    |
| 먼저 만들고 물어보기 | **설계 먼저, 구현은 나중** |
| 불명확한데 진행      | **의심되면 물어보기**      |

---

## 📍 빠른 링크

- **프로젝트 메모리**: `.claude/projects/-Users-teamgrit-Documents-CoWater/memory/`
- **프로젝트 아키텍처**: `docs/SYSTEM_ARCHITECTURE.md`
- **빠른 시작**: `docs/QUICK_START.md`
- **Git Hooks**: `.git/hooks/pre-commit`, `pre-push`

---

**Remember**: 이 규칙들이 있어야 Claude가 **안전하고 정확**하게 동작합니다.  
**모든 규칙보다 우선**: 의심되면 물어보기! 🛡️

---

## 에이전트 스킬

### 이슈 추적기

이슈는 GitHub Issues에서 관리합니다.

자주 쓰는 명령:

```bash
gh issue create --title "..." --body "..."
gh issue view <number>
gh issue list --label needs-triage
```

### 트리아지 라벨

이슈는 아래 다섯 개의 표준 트리아지 라벨을 사용합니다.

| 라벨              | 의미                                 | 다음 단계                               |
| ----------------- | ------------------------------------ | --------------------------------------- |
| `needs-triage`    | 관리자의 1차 검토가 필요함           | → `needs-info` 또는 `ready-for-agent`   |
| `needs-info`      | 제보자의 추가 설명을 기다림          | → `needs-triage` 또는 `ready-for-agent` |
| `ready-for-agent` | 사양이 충분해 에이전트가 작업 가능함 | → 필요 시 `ready-for-human`             |
| `ready-for-human` | 사람이 직접 구현해야 함              | 종료 상태                               |
| `wontfix`         | 처리하지 않기로 결정함               | 종료 상태                               |

라벨 조작 예시:

```bash
gh issue edit <number> --add-label needs-triage
gh issue edit <number> --remove-label needs-info
```

이 라벨 체계가 있으면 `triage` 스킬이 별도 커스텀 연동 없이도 이슈 흐름을 자동화할 수 있습니다.

### 도메인 문서

CoWater는 도메인 언어와 아키텍처 결정을 한 곳에서 추적하는 단일 컨텍스트 구성을 사용합니다.

- `CONTEXT.md` — 도메인 언어, 핵심 개념, 아키텍처 용어
- `docs/adr/` — 주요 설계 결정을 담은 ADR 모음
- `.claude/COWATER_CONTEXT.md` — 시스템 빠른 참고 문서

문서 갱신 기준:

- 새 개념이나 용어를 추가할 때 → `CONTEXT.md` 갱신
- 아키텍처 결정을 내릴 때 → `docs/adr/`에 ADR 추가 후 `docs/adr/ADR-000-index.md` 갱신
- 용어 충돌을 발견했을 때 → `CONTEXT.md`와 관련 ADR을 함께 갱신

`improve-codebase-architecture`, `diagnose`, `tdd` 같은 스킬은 이 문서들을 기준으로 도메인 제약과 용어를 해석합니다.
