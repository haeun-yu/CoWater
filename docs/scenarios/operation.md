# 작업 프로세스 (Operation Process)

작업 제안 → 승인 → 실행의 전체 흐름

## 프로세스 플로우

```
1. Agent가 미션 분석
   ↓
2. Operation 제안 (LLM 기반)
   ↓
3. 관리자/User 검토
   ↓
4. 승인 또는 거절
   ↓
5. 승인된 작업 실행
   ↓
6. 결과 기록 및 다음 제안
```

## 각 단계별 책임

| 단계 | 책임자 | 시스템 | 결과 |
|------|--------|--------|------|
| 제안 | Agent (LLM) | - | Operation.proposed |
| 검토 | 관리자 | 승인/거절 UI | Operation.approved/rejected |
| 실행 | 시스템 | 작업 실행 엔진 | Operation.executed |
| 기록 | 플랫폼 | 데이터 저장 | 로그 및 감사 추적 |

## LLM 기반 제안 (Agent)

- **입력**: Mission 상태, 이전 작업 이력, 현재 환경
- **처리**: Anthropic Claude API를 통한 분석
- **출력**: 다음 단계 작업 제안

## 참고

- `lifecycle.md` - 미션 상태 관리
- `exceptions.md` - 실패 및 대응
- `SYSTEM_ARCHITECTURE.md` - 에이전트 구현
