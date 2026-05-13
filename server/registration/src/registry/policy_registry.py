"""
PolicyRegistry: 정책 저장소 및 평가 엔진

사전 정의된 정책이 있는 Critical 상황에서 제한적 자동 대응이 가능.
(아키텍처 Ch.17.1)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from src.db.connection import DatabaseConnection, get_db

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PolicyRegistry:
    """SQLite-backed 정책 저장소"""

    def __init__(self, db_path: str | None = None) -> None:
        self.db: DatabaseConnection = get_db(db_path)
        self._init_db()
        self._seed_default_policies()

    def _connect(self) -> sqlite3.Connection:
        return self.db.get_connection()

    def _init_db(self) -> None:
        conn = self._connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS policies (
                policy_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_policies_policy_id ON policies(policy_id)")
        conn.commit()

    def _seed_default_policies(self) -> None:
        # Migrate the old "lost" wording to the docs-standard "offline" state.
        self.db.execute("DELETE FROM policies WHERE policy_id = ?", ("auto_rtb_on_lost",))
        self.db.commit()

        default_policies = [
            {
                "policy_id": "auto_rtb_on_offline",
                "policy_name": "Offline Device Return to Base",
                "name": "auto_rtb_on_offline",
                "description": "Offline device triggers return-to-base mission proposal.",
                "enabled": True,
                "trigger_condition": {
                    "event_type": "device_connectivity_changed",
                    "new_status": "offline",
                },
                "action": {
                    "task_type": "return_to_base",
                    "priority": "critical",
                },
            },
            {
                "policy_id": "alert_low_battery",
                "policy_name": "Low Battery Alert",
                "name": "alert_low_battery",
                "description": "Low battery only emits an alert and does not auto-remediate.",
                "enabled": True,
                "trigger_condition": {
                    "event_type": "battery_low",
                    "threshold": 20,
                },
                "action": {
                    "type": "alert_only",
                },
            },
        ]
        for policy in default_policies:
            if self._read_row(str(policy["policy_id"])) is None:
                self.create_policy(policy)

    def _read_row(self, policy_id: str) -> dict[str, Any] | None:
        cursor = self.db.execute(
            "SELECT policy_id, data, created_at, updated_at FROM policies WHERE policy_id = ?",
            (policy_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        data = json.loads(row["data"])
        data.setdefault("policy_id", row["policy_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return data

    def get_policies(self) -> list[dict[str, Any]]:
        return self.list_policies()

    def list_policies(self, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        query = "SELECT policy_id, data, created_at, updated_at FROM policies ORDER BY policy_id"
        params: list[int] = []
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
            if offset:
                query += " OFFSET ?"
                params.append(offset)
        elif offset:
            query += " LIMIT -1 OFFSET ?"
            params.append(offset)
        cursor = self.db.execute(query, tuple(params))
        rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            data = json.loads(row["data"])
            data.setdefault("policy_id", row["policy_id"])
            data.setdefault("created_at", row["created_at"])
            data.setdefault("updated_at", row["updated_at"])
            result.append(data)
        return result

    def get_policy(self, policy_id: str) -> Optional[dict[str, Any]]:
        return self._read_row(policy_id)

    def create_policy(self, policy: dict[str, Any]) -> dict[str, Any]:
        policy_id = str(policy.get("policy_id") or policy.get("id") or uuid4())
        now = utc_now_iso()
        existing = self._read_row(policy_id) or {}
        record = deepcopy(existing)
        record.update(policy)
        record["policy_id"] = policy_id
        record.setdefault("name", record.get("policy_name") or policy_id)
        record.setdefault("policy_name", record.get("name") or policy_id)
        record.setdefault("enabled", True)
        record["created_at"] = existing.get("created_at") or now
        record["updated_at"] = now
        self.db.execute(
            """
            INSERT OR REPLACE INTO policies (policy_id, data, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (policy_id, json.dumps(record, ensure_ascii=False), record["created_at"], now),
        )
        self.db.commit()
        logger.info(f"Policy created: {policy_id} - {record.get('policy_name')}")
        return record

    def update_policy(self, policy_id: str, policy: dict[str, Any]) -> dict[str, Any]:
        existing = self._read_row(policy_id)
        if existing is None:
            existing = {"policy_id": policy_id, "created_at": utc_now_iso()}
        record = deepcopy(existing)
        record.update(policy)
        record["policy_id"] = policy_id
        record.setdefault("name", record.get("policy_name") or policy_id)
        record.setdefault("policy_name", record.get("name") or policy_id)
        record["updated_at"] = utc_now_iso()
        self.db.execute(
            """
            INSERT OR REPLACE INTO policies (policy_id, data, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                policy_id,
                json.dumps(record, ensure_ascii=False),
                existing.get("created_at") or record["updated_at"],
                record["updated_at"],
            ),
        )
        self.db.commit()
        logger.info(f"Policy updated: {policy_id}")
        return record

    def delete_policy(self, policy_id: str) -> None:
        self.db.execute("DELETE FROM policies WHERE policy_id = ?", (policy_id,))
        self.db.commit()
        logger.info(f"Policy deleted: {policy_id}")

    def reset(self) -> None:
        self.db.execute("DELETE FROM policies")
        self.db.commit()
        self._seed_default_policies()

    def find_policies_by_trigger(self, event_type: str) -> list[dict[str, Any]]:
        matched = []
        for policy in self.list_policies():
            if not policy.get("enabled"):
                continue
            trigger = policy.get("trigger_condition") or {}
            if trigger.get("event_type") == event_type:
                matched.append(policy)
        return matched

    def evaluate_condition(self, condition: dict[str, Any], event: dict[str, Any]) -> bool:
        event_type = condition.get("event_type")
        if event.get("event_type") != event_type:
            return False

        for key, expected_value in condition.items():
            if key == "event_type":
                continue
            event_value = event.get(key)
            if event_value != expected_value:
                return False

        return True
