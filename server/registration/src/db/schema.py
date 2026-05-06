"""SQLite Schema definitions for CoWater Mission Tracking"""

SCHEMA_VERSION = 1

# Mission 테이블 스키마
MISSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS missions (
    mission_id TEXT PRIMARY KEY,
    response_id TEXT NOT NULL UNIQUE,
    alert_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    step_states TEXT DEFAULT '[]',
    completion_report TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (response_id) REFERENCES responses(response_id),
    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
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
CREATE INDEX IF NOT EXISTS idx_missions_response_id ON missions(response_id);
CREATE INDEX IF NOT EXISTS idx_missions_alert_id ON missions(alert_id);
CREATE INDEX IF NOT EXISTS idx_missions_status ON missions(status);
CREATE INDEX IF NOT EXISTS idx_missions_created_at ON missions(created_at);
"""


def init_schema(conn):
    """Initialize database schema"""
    cursor = conn.cursor()
    
    # Check schema version
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    result = cursor.fetchone()
    current_version = result[0] if result else 0
    
    if current_version < SCHEMA_VERSION:
        # Apply schema updates
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(SCHEMA_VERSION_TABLE)
        cursor.execute(MISSIONS_TABLE)
        cursor.execute(MISSIONS_INDEXES)
        
        # Update schema version
        from datetime import datetime, timezone
        cursor.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        
        return True
    
    return False
