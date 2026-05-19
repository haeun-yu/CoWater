"""SQLite Schema definitions for CoWater Mission Tracking"""

SCHEMA_VERSION = 4

# User 테이블
USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Agent 테이블
AGENTS_TABLE = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Mission 테이블 (수정: response_id, alert_id 제거 → source_proposal_id, source_event_id 추가)
MISSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    source_event_id TEXT,
    source_proposal_id TEXT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# ProposalTask 테이블
PROPOSAL_TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS proposal_tasks (
    task_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (proposal_id) REFERENCES domain_records(record_id)
);
"""

# Task 테이블
TASKS_TABLE = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (mission_id) REFERENCES missions(mission_id)
);
"""

# Report 테이블
REPORTS_TABLE = """
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# Rule 테이블
RULES_TABLE = """
CREATE TABLE IF NOT EXISTS rules (
    rule_id TEXT PRIMARY KEY,
    policy_id TEXT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (policy_id) REFERENCES policies(policy_id)
);
"""

# Config 테이블
CONFIGS_TABLE = """
CREATE TABLE IF NOT EXISTS configs (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Sensor 테이블
SENSORS_TABLE = """
CREATE TABLE IF NOT EXISTS sensors (
    sensor_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# Schema version tracking
SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);
"""

# 인덱스 생성 (성능 최적화)
MISSIONS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_missions_source_event_id ON missions(source_event_id);
CREATE INDEX IF NOT EXISTS idx_missions_source_proposal_id ON missions(source_proposal_id);
CREATE INDEX IF NOT EXISTS idx_missions_created_at ON missions(created_at);
"""

PROPOSAL_TASKS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_proposal_tasks_proposal_id ON proposal_tasks(proposal_id);
"""

TASKS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_tasks_mission_id ON tasks(mission_id);
"""

RULES_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_rules_policy_id ON rules(policy_id);
"""

SENSORS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_sensors_device_id ON sensors(device_id);
"""

DOMAIN_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS domain_records (
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (record_type, record_id)
);
"""

DOMAIN_RECORDS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_domain_records_type ON domain_records(record_type);
"""

POLICIES_TABLE = """
CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

POLICIES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_policies_policy_id ON policies(policy_id);
"""


def init_schema(conn):
    """Initialize database schema"""
    cursor = conn.cursor()

    cursor.execute(SCHEMA_VERSION_TABLE)

    # Check schema version
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    result = cursor.fetchone()
    current_version = result[0] if result else 0

    if current_version < SCHEMA_VERSION:
        # Apply schema updates
        cursor.execute("PRAGMA foreign_keys = ON")

        # Create new domain tables (v4)
        cursor.execute(USERS_TABLE)
        cursor.execute(AGENTS_TABLE)
        cursor.execute(MISSIONS_TABLE)
        cursor.executescript(MISSIONS_INDEXES)
        cursor.execute(PROPOSAL_TASKS_TABLE)
        cursor.executescript(PROPOSAL_TASKS_INDEXES)
        cursor.execute(TASKS_TABLE)
        cursor.executescript(TASKS_INDEXES)
        cursor.execute(REPORTS_TABLE)
        cursor.execute(RULES_TABLE)
        cursor.executescript(RULES_INDEXES)
        cursor.execute(CONFIGS_TABLE)
        cursor.execute(SENSORS_TABLE)
        cursor.executescript(SENSORS_INDEXES)

        # Create generic domain records table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='domain_records'")
        has_domain_records = cursor.fetchone() is not None
        if has_domain_records and current_version < 3:
            cursor.execute("ALTER TABLE domain_records RENAME TO domain_records_legacy")
            cursor.execute(DOMAIN_RECORDS_TABLE)
            cursor.execute(DOMAIN_RECORDS_INDEX)
            cursor.execute(
                """
                INSERT OR REPLACE INTO domain_records (record_type, record_id, data, created_at, updated_at)
                SELECT record_type, record_id, data, created_at, updated_at
                FROM domain_records_legacy
                """
            )
            cursor.execute("DROP TABLE domain_records_legacy")
        else:
            cursor.execute(DOMAIN_RECORDS_TABLE)
            cursor.execute(DOMAIN_RECORDS_INDEX)

        cursor.execute(POLICIES_TABLE)
        cursor.execute(POLICIES_INDEX)

        # Update schema version
        from datetime import datetime, timezone
        cursor.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()

        return True

    return False
