-- ============================================================
-- Migration: dedup_key 컬럼 추가 및 alert_type CHECK 확장
-- 기존 실행 중인 DB 인스턴스에 적용
-- ============================================================

-- 1) dedup_key 컬럼 추가 (없는 경우에만)
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS dedup_key TEXT;

-- 2) 기존 metadata JSONB에서 dedup_key 값 마이그레이션
UPDATE alerts
SET    dedup_key = metadata ->> 'dedup_key'
WHERE  dedup_key IS NULL
  AND  metadata ->> 'dedup_key' IS NOT NULL;

-- 3) 새 dedup 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_alerts_dedup_key
    ON alerts (generated_by, dedup_key)
    WHERE status = 'new';

-- 4) alert_type CHECK 제약 확장 (zone_exit, ais_recovered 추가)
ALTER TABLE alerts DROP CONSTRAINT IF EXISTS alerts_alert_type_check;
ALTER TABLE alerts ADD CONSTRAINT alerts_alert_type_check
    CHECK (alert_type IN (
        'cpa','zone_intrusion','zone_exit','anomaly',
        'ais_off','ais_recovered','distress','compliance','traffic'
    ));
