# 문서 관리 3대 규칙 (AI 에이전트용)

효율적인 문서 관리를 위한 AI 에이전트 지시 규칙

---

## ① 중복 배제의 원칙 (Single Source of Truth)

**규칙**: 상태값이나 데이터 구조의 상세 내용은 `docs/core/schema.md`에 한 번만 정의  
`docs/scenarios/*.md`에서는 해당 필드명만 언급하거나 링크를 걸기

**이유**: 스키마가 바뀌어도 `docs/core/schema.md`만 수정하면 전체 문서의 일관성을 유지할 수 있습니다.

**적용 방법**:
- ❌ `scenarios/operation.md`에서 Operation의 구조를 다시 설명하지 않기
- ✅ `scenarios/operation.md`에서 "자세한 필드는 [schema.md](../core/schema.md#operation) 참고"라고 링크하기
- ✅ `scenarios/`에서는 **개념과 흐름**만 중심으로 작성

---

## ② 다이어그램은 텍스트 코드로 작성

**규칙**: 모든 시퀀스 다이어그램, 플로우 차트는 **이미지 파일이 아니라 Mermaid 코드**로 작성

**이유**: 
- AI가 다이어그램을 직접 수정 가능
- 마크다운 뷰어에서 자동으로 렌더링
- 웹 코드 변환 시 쉽게 통합

**적용 방법**:
```markdown
## 프로세스 플로우

\`\`\`mermaid
graph TD
    A[미션 등록] --> B[작업 제안]
    B --> C{승인?}
    C -->|yes| D[실행]
    C -->|no| E[거절]
\`\`\`
```

---

## ③ ADR 기반으로 업데이트

**규칙**: 새로운 기능 추가 또는 아키텍처 변경 시, **반드시 먼저 ADR에 결정을 기록**한 후 문서 업데이트

**이유**: 
- 왜 그렇게 결정했는지 이력 남김
- 추후 논의/롤백 시 결정 근거 확인 가능
- 팀 전체가 의도 이해

**적용 방법**:
1. `docs/adr/ADR-00X-*.md` 작성 (상황, 결정, 결과)
2. `docs/adr/ADR-000-index.md`에 등재
3. 그 결정에 따라 `docs/core/` 및 `docs/scenarios/` 업데이트
4. 관련 다른 ADR 참고 표시

> **관리자 주의**: `docs/adr/ADR-007-data-generalization.md`가 존재하지만
> `docs/adr/ADR-000-index.md`에 등재되지 않았습니다.
> ADR을 추가하거나 편집할 때 반드시 index 파일도 갱신하세요.

---

## 보너스: "추후 반영" 항목 처리

대화 중 "그건 추후에 반영할거야"라는 결정이 나오면  
→ **docs/roadmap.md**의 적절한 섹션에 추가하기

**적용 방법**:
```markdown
## 진행 중
- [ ] 미션 분리 (ADR-001 검토 중)  
- [ ] Agent 기능 확장 ← 추가된 새 항목
```

---

## ⚠️ ADR 번호 관리 규칙

**규칙**: ADR 번호는 **순차적이어야 함** (건너뛰지 말 것)

**기본 원칙**:
- ADR-001~006: 핵심 설계 철학 및 패턴 (변경 X)
- ADR-007+: 새로운 기술 결정 사항 (순차적으로 생성)
- **반드시 ADR-000-index.md에 즉시 등재**
- 모든 관련 문서에서 참고 링크 업데이트

**현재 상태**: ADR-001~009까지 정의 (ADR-010은 사용 금지)

---

## 적용 예시

**시나리오**: "Operation에 priority 필드를 추가하고 싶다"

```
【PROCESS】
1. 현재 최신 ADR 번호 확인 (docs/adr/ADR-000-index.md)
   → 현재 최신: ADR-009
   → 다음 번호: ADR-010 (순차 증가)

2. docs/adr/ADR-010-operation-priority-management.md 작성
   - 상황: Operation 우선순위 관리 필요
   - 결정: priority 필드 추가 (int, 1-5)
   - 결과: 작업 실행 순서를 동적으로 변경 가능

3. docs/adr/ADR-000-index.md 즉시 업데이트
   - 표에 새 행 추가
   - 정확한 링크 확인

4. 모든 관련 문서에서 ADR 참고 업데이트
   - docs/SYSTEM_ARCHITECTURE.md (Section 6 ADR 참고)
   - docs/core/schema.md
   - docs/scenarios/*.md
   - .claude/*.md

5. docs/core/schema.md 업데이트
   - Operation JSON에 priority 필드 추가

6. docs/scenarios/operation.md 업데이트
   - "우선순위에 따라 작업 실행" 절차 추가
   - ADR-010 참고 추가
   - schema.md의 priority 필드 링크

7. docs/scenarios/lifecycle.md 검토
   - 생명주기에 영향 있는지 확인
```

**검사 체크리스트**:
- [ ] ADR-000-index.md에 새 ADR 등재됨?
- [ ] 새 ADR 번호 = (이전 최신 번호 + 1)?
- [ ] 모든 관련 문서에서 ADR 참고 업데이트됨?
- [ ] 시나리오/코어 문서에서 불일치 없음?

---

## 참고
- `PROCESS.md` - 기능 구현 절차
- `COWATER_CONTEXT.md` - 시스템 컨텍스트
- `GUIDELINES.md` - 일반 개발 가이드라인
