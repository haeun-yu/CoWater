# 핵심 도메인 모델 (Domain Model)

**Ubiquitous Language** - 모든 팀이 공유하는 도메인 개념 정의

## 주요 엔티티

### Mission (미션)
- **정의**: 해양 작업의 작은 단위 업무
- **상태**: Registered → Active → Completed / Cancelled
- **책임**: 작업 식별, 추적, 보고

### Agent (에이전트)
- **정의**: 미션 실행을 담당하는 AI 시스템
- **역할**: LLM 활용 자동 판단 및 추천

### Operation (작업)
- **정의**: 미션을 구성하는 구체적인 수행 항목
- **상태**: Proposed → Approved → Executed

## 도메인 이벤트

- `MissionRegistered` - 새로운 미션 등록
- `MissionActivated` - 미션 활성화
- `MissionCompleted` - 미션 완료
- `OperationProposed` - 작업 제안
- `OperationApproved` - 작업 승인

## 참고

- `principles.md` - 설계 원칙
- `schema.md` - 데이터 스키마
