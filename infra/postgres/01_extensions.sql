-- UUID extension 명시적 설치
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" CASCADE;

-- PostGIS + TimescaleDB extensions
CREATE EXTENSION IF NOT EXISTS postgis;
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS timescaledb;
EXCEPTION
    WHEN undefined_file OR feature_not_supported THEN
        NULL;
END
$$;
