-- UUID extension 명시적 설치
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" CASCADE;

-- PostGIS + TimescaleDB extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb;
