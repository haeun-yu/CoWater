-- ============================================================
-- CoWater Schema
-- ============================================================

-- ------------------------------------------------------------
-- platforms
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platforms (
    platform_id     TEXT PRIMARY KEY,
    platform_type   TEXT NOT NULL CHECK (platform_type IN ('vessel','rov','usv','auv','drone','buoy')),
    name            TEXT NOT NULL,
    flag            TEXT,
    source_protocol TEXT NOT NULL CHECK (source_protocol IN ('ais','ros','mavlink','nmea','custom')),
    moth_channel    TEXT,               -- Moth 채널명
    capabilities    TEXT[] NOT NULL DEFAULT '{}',
    dimensions      JSONB,              -- { length_m, beam_m, draft_m }
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- platform_reports  (TimescaleDB Hypertable)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_reports (
    time            TIMESTAMPTZ     NOT NULL,
    platform_id     TEXT            NOT NULL REFERENCES platforms(platform_id) ON DELETE CASCADE,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    depth_m         REAL,
    altitude_m      REAL,
    sog             REAL,           -- knots
    cog             REAL,           -- degrees
    heading         REAL,           -- degrees
    rot             REAL,           -- degrees/min
    nav_status      TEXT,
    source_protocol TEXT NOT NULL,
    raw_payload     BYTEA
);

-- Create hypertable if TimescaleDB is available, otherwise skip
DO $$
BEGIN
    BEGIN
        PERFORM create_hypertable(
            'platform_reports', 'time',
            partitioning_column => 'platform_id',
            number_partitions   => 4,
            if_not_exists       => TRUE
        );
    EXCEPTION WHEN OTHERS THEN
        -- TimescaleDB not available, continue with regular table
        RAISE NOTICE 'TimescaleDB extension not available, using regular table instead';
    END;
END $$;

-- 최근 데이터 조회 최적화
CREATE INDEX IF NOT EXISTS idx_reports_platform_time
    ON platform_reports (platform_id, time DESC);

-- 공간 쿼리용 (PostGIS 포인트 — 필요 시 computed column 추가 가능)
CREATE INDEX IF NOT EXISTS idx_reports_location
    ON platform_reports USING BRIN (lat, lon);

-- ------------------------------------------------------------
-- zones
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS zones (
    zone_id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    zone_type   TEXT NOT NULL CHECK (zone_type IN (
                    'fairway','restricted','prohibited',
                    'anchorage','tss','precautionary'
                )),
    geometry    GEOMETRY(Geometry, 4326) NOT NULL,
    rules       JSONB NOT NULL DEFAULT '{}',  -- { speed_limit, entry_restriction, ... }
    active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_zones_geometry
    ON zones USING GIST (geometry);

CREATE INDEX IF NOT EXISTS idx_zones_type
    ON zones (zone_type) WHERE active = TRUE;

-- ------------------------------------------------------------
-- alerts
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    alert_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type      TEXT NOT NULL CHECK (alert_type IN (
                        'cpa','zone_intrusion','zone_exit','anomaly',
                        'ais_off','ais_recovered','distress','compliance','traffic'
                    )),
    severity        TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
    status          TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','acknowledged','resolved')),
    platform_ids    TEXT[] NOT NULL DEFAULT '{}',
    zone_id         UUID REFERENCES zones(zone_id),
    generated_by    TEXT NOT NULL,      -- Agent ID
    message         TEXT NOT NULL,
    recommendation  TEXT,               -- AI Agent 권고사항
    metadata        JSONB NOT NULL DEFAULT '{}',
    -- dedup_key: 중복 경보 방지용 전용 컬럼 (JSONB 경로 쿼리 대비 빠른 인덱스 지원)
    dedup_key       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_status     ON alerts (status);
CREATE INDEX IF NOT EXISTS idx_alerts_severity   ON alerts (severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_platforms  ON alerts USING GIN (platform_ids);
CREATE INDEX IF NOT EXISTS idx_alerts_dedup_key  ON alerts (generated_by, dedup_key) WHERE status = 'new';

-- ------------------------------------------------------------
-- incidents
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
    incident_id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_type   TEXT NOT NULL,
    alert_ids       UUID[] NOT NULL DEFAULT '{}',
    platform_ids    TEXT[] NOT NULL DEFAULT '{}',
    timeline        JSONB NOT NULL DEFAULT '[]',
    resolved        BOOLEAN NOT NULL DEFAULT FALSE,
    report          TEXT,               -- AI 생성 보고서
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- audit_logs  (불변 — UPDATE/DELETE 금지)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type  TEXT NOT NULL,
    actor       TEXT,                   -- operator ID or agent ID
    entity_type TEXT,                   -- 'platform', 'alert', 'agent', ...
    entity_id   TEXT,
    payload     JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_entity
    ON audit_logs (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created_at
    ON audit_logs (created_at DESC);

-- 불변 보장: UPDATE / DELETE 차단
CREATE OR REPLACE RULE audit_no_update AS ON UPDATE TO audit_logs DO INSTEAD NOTHING;
CREATE OR REPLACE RULE audit_no_delete AS ON DELETE TO audit_logs DO INSTEAD NOTHING;
