# 공통 데이터 스키마 (Common Schema)

주요 데이터 모델의 JSON/SQL 상세 정의

## Mission

```json
{
  "id": "uuid",
  "name": "string",
  "description": "string",
  "status": "enum[registered, active, completed, cancelled]",
  "vessel_id": "uuid",
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "completed_at": "timestamp | null"
}
```

## Operation

```json
{
  "id": "uuid",
  "mission_id": "uuid",
  "type": "string",
  "description": "string",
  "status": "enum[proposed, approved, executed, failed]",
  "proposed_by": "uuid",
  "approved_by": "uuid | null",
  "executed_at": "timestamp | null",
  "created_at": "timestamp"
}
```

## SQL Schema

(상세 스키마는 데이터베이스 마이그레이션 파일 참고)

- `services/platform/migrations/`
- TimescaleDB + PostGIS 활용

## 참고

- `domain-model.md` - 도메인 정의
- `SYSTEM_ARCHITECTURE.md` - 서비스 구조
