#!/usr/bin/env bash
# ============================================================
# CoWater DB 마이그레이션 실행 스크립트
#
# 사용법:
#   cd infra && bash ../scripts/migrate.sh
#
# 사전 조건: docker compose로 postgres 컨테이너가 실행 중이어야 합니다.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
INFRA_DIR="$REPO_ROOT/infra"

PG_CONTAINER="${PG_CONTAINER:-cowater-postgres}"
PG_USER="${PG_USER:-cowater}"
PG_DB="${PG_DB:-cowater}"

echo "[migrate] PostgreSQL 컨테이너: $PG_CONTAINER"
echo "[migrate] 대상 DB: $PG_DB"

# 컨테이너 실행 여부 확인
if ! docker ps --format '{{.Names}}' | grep -q "^${PG_CONTAINER}$"; then
  echo "[migrate] ERROR: 컨테이너 '$PG_CONTAINER'가 실행 중이지 않습니다."
  echo "          cd infra && docker compose up -d postgres"
  exit 1
fi

# 마이그레이션 파일 목록 (숫자 순서로 실행, 04_ 이상만)
MIGRATION_FILES=$(ls "$INFRA_DIR"/postgres/0[4-9]_*.sql 2>/dev/null || true)

if [ -z "$MIGRATION_FILES" ]; then
  echo "[migrate] 실행할 마이그레이션 파일이 없습니다."
  exit 0
fi

for FILE in $MIGRATION_FILES; do
  BASENAME="$(basename "$FILE")"
  echo "[migrate] 실행 중: $BASENAME"
  docker exec -i "$PG_CONTAINER" \
    psql -U "$PG_USER" -d "$PG_DB" \
    < "$FILE"
  echo "[migrate] 완료: $BASENAME"
done

echo "[migrate] 모든 마이그레이션 완료."
