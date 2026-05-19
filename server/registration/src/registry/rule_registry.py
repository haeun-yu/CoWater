from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import RuleRecord
from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_RULES_SQL = """
CREATE TABLE IF NOT EXISTS rules (
    rule_id TEXT PRIMARY KEY,
    policy_id TEXT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_rules_policy_id ON rules(policy_id)
"""


class RuleRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/rules.db"

        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(_CREATE_RULES_SQL)
                conn.execute(_CREATE_INDEX_SQL)
                conn.commit()
            logger.info(f"RuleRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"RuleRegistry DB 초기화 실패: {e}")

    def _row_to_rule(self, row: sqlite3.Row) -> RuleRecord:
        data = json.loads(row["data"])
        data.setdefault("rule_id", row["rule_id"])
        data.setdefault("policy_id", row["policy_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return RuleRecord(**data)

    def _persist_rule(self, rule: RuleRecord) -> None:
        data = rule.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO rules (rule_id, policy_id, data, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (rule.rule_id, rule.policy_id, json.dumps(data), rule.created_at, rule.updated_at),
            )
            conn.commit()

    def create_rule(
        self,
        rule_type: str,
        name: str,
        enabled: bool,
        priority: int,
        conditions: list,
        action: dict,
        severity: str = "INFO",
        policy_id: str | None = None,
        created_by: dict | None = None,
    ) -> RuleRecord:
        """새 Rule 생성"""
        rule = RuleRecord(
            rule_id=str(uuid4()),
            rule_type=rule_type,
            name=name,
            enabled=enabled,
            priority=priority,
            conditions=conditions,
            action=action,
            severity=severity,
            policy_id=policy_id,
            created_by=created_by or {"type": "SYSTEM", "id": "system"},
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self._persist_rule(rule)
        return rule

    def get_rule(self, rule_id: str) -> RuleRecord:
        """Rule 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT rule_id, policy_id, data, created_at, updated_at FROM rules WHERE rule_id = ?",
                (rule_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Rule not found: {rule_id}")
            return self._row_to_rule(row)

    def list_rules(self, limit: int = 100, offset: int = 0) -> List[RuleRecord]:
        """Rule 목록 조회"""
        query = "SELECT rule_id, policy_id, data, created_at, updated_at FROM rules ORDER BY created_at DESC"
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
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_rule(row) for row in rows]

    def list_rules_by_policy(self, policy_id: str) -> List[RuleRecord]:
        """Policy별 Rule 목록 조회"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT rule_id, policy_id, data, created_at, updated_at FROM rules WHERE policy_id = ? ORDER BY data->'$.priority'",
                (policy_id,)
            ).fetchall()
            return [self._row_to_rule(row) for row in rows]

    def list_enabled_rules(self) -> List[RuleRecord]:
        """활성화된 Rule 목록 조회"""
        rules = []
        with self._connect() as conn:
            rows = conn.execute("SELECT rule_id, policy_id, data, created_at, updated_at FROM rules").fetchall()
            for row in rows:
                rule = self._row_to_rule(row)
                if rule.enabled:
                    rules.append(rule)
        return sorted(rules, key=lambda r: r.priority)

    def update_rule(self, rule_id: str, **kwargs) -> RuleRecord:
        """Rule 업데이트"""
        rule = self.get_rule(rule_id)
        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        rule.updated_at = utc_now_iso()
        self._persist_rule(rule)
        return rule

    def delete_rule(self, rule_id: str) -> None:
        """Rule 삭제"""
        with self._connect() as conn:
            conn.execute("DELETE FROM rules WHERE rule_id = ?", (rule_id,))
            conn.commit()

    def reset(self) -> None:
        """모든 Rule 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM rules")
            conn.commit()
        logger.info("RuleRegistry 초기화 완료")
