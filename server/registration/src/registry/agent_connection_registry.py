from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List
from uuid import uuid4

from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_AGENT_CONNECTIONS_SQL = """
CREATE TABLE IF NOT EXISTS agent_connections (
    connection_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


@dataclass
class AgentConnectionRecord:
    connection_id: str
    agent_a_id: str
    agent_b_id: str
    connection_type: str
    relation_level: str = "PEER"           # "PEER" | "PARENT_CHILD" — PARENT_CHILD 시 parent_agent_id 필수
    parent_agent_id: str | None = None     # PARENT_CHILD 인 경우만 설정
    mission_id: str | None = None
    reason: str | None = None
    profile: dict[str, Any] = field(default_factory=lambda: {
        "endpoint_a": None,
        "endpoint_b": None,
        "protocol": "A2A",
        "transport": "HTTP",
        "network_type": None,
        "signal_strength": None,
        "latency_ms": None,
        "bandwidth_mbps": None,
        "auth_info_ref": None,
        "expires_at": None,
    })
    deleted_at: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connection_id": self.connection_id,
            "id": self.connection_id,
            "agent_a_id": self.agent_a_id,
            "agent_b_id": self.agent_b_id,
            "connection_type": str(self.connection_type).upper(),
            "relation_level": str(self.relation_level).upper(),
            "parent_agent_id": self.parent_agent_id,
            "mission_id": self.mission_id,
            "reason": self.reason,
            "profile": self.profile,
            "deleted_at": self.deleted_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class AgentConnectionRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/agent_connections.db"

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
                conn.execute(_CREATE_AGENT_CONNECTIONS_SQL)
                conn.commit()
            logger.info(f"AgentConnectionRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"AgentConnectionRegistry DB 초기화 실패: {e}")

    def _row_to_agent_connection(self, row: sqlite3.Row) -> AgentConnectionRecord:
        data = json.loads(row["data"])
        data.setdefault("connection_id", row["connection_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return AgentConnectionRecord(**data)

    def _persist_agent_connection(self, agent_connection: AgentConnectionRecord) -> None:
        data = agent_connection.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agent_connections (connection_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (agent_connection.connection_id, json.dumps(data), agent_connection.created_at, agent_connection.updated_at),
            )
            conn.commit()

    @staticmethod
    def _build_profile(payload: dict[str, Any]) -> dict[str, Any]:
        """payload 또는 기본값으로 schema 정의 profile 구성"""
        provided = payload.get("profile") or {}
        return {
            "endpoint_a": provided.get("endpoint_a") or payload.get("endpoint_a"),
            "endpoint_b": provided.get("endpoint_b") or payload.get("endpoint_b"),
            "protocol": provided.get("protocol") or "A2A",
            "transport": provided.get("transport") or "HTTP",
            "network_type": provided.get("network_type"),
            "signal_strength": provided.get("signal_strength"),
            "latency_ms": provided.get("latency_ms"),
            "bandwidth_mbps": provided.get("bandwidth_mbps"),
            "auth_info_ref": provided.get("auth_info_ref"),
            "expires_at": provided.get("expires_at"),
        }

    def create_agent_connection(self, payload: dict[str, Any]) -> AgentConnectionRecord:
        """Agent Connection 생성"""
        connection_id = str(payload.get("connection_id") or payload.get("id") or f"conn-{uuid4()}")
        agent_connection = AgentConnectionRecord(
            connection_id=connection_id,
            agent_a_id=str(payload.get("agent_a_id") or ""),
            agent_b_id=str(payload.get("agent_b_id") or ""),
            connection_type=str(payload.get("connection_type") or "RELAY"),
            relation_level=str(payload.get("relation_level") or "PEER"),
            parent_agent_id=payload.get("parent_agent_id"),
            mission_id=payload.get("mission_id"),
            reason=payload.get("reason"),
            profile=self._build_profile(payload),
            deleted_at=payload.get("deleted_at"),
        )
        self._persist_agent_connection(agent_connection)
        return agent_connection

    def get_agent_connection(self, connection_id: str) -> AgentConnectionRecord:
        """Agent Connection 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT connection_id, data, created_at, updated_at FROM agent_connections WHERE connection_id = ?",
                (connection_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Agent connection not found: {connection_id}")
            return self._row_to_agent_connection(row)

    def list_agent_connections(self, limit: int | None = None, offset: int = 0) -> List[AgentConnectionRecord]:
        """Agent Connection 목록 조회"""
        query = "SELECT connection_id, data, created_at, updated_at FROM agent_connections ORDER BY created_at, connection_id"
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
        return [self._row_to_agent_connection(row) for row in rows]

    def update_agent_connection(self, connection_id: str, payload: dict[str, Any]) -> AgentConnectionRecord:
        """Agent Connection 업데이트"""
        connection = self.get_agent_connection(connection_id)
        # 기존 필드 유지하고 업데이트만 적용
        update_data = {
            "agent_a_id": payload.get("agent_a_id", connection.agent_a_id),
            "agent_b_id": payload.get("agent_b_id", connection.agent_b_id),
            "connection_type": payload.get("connection_type", connection.connection_type),
            "relation_level": payload.get("relation_level", connection.relation_level),
            "parent_agent_id": payload.get("parent_agent_id", connection.parent_agent_id),
            "mission_id": payload.get("mission_id", connection.mission_id),
            "reason": payload.get("reason", connection.reason),
            "profile": payload.get("profile", connection.profile),
            "deleted_at": payload.get("deleted_at", connection.deleted_at),
        }

        updated = AgentConnectionRecord(
            connection_id=connection_id,
            **update_data,
            created_at=connection.created_at,
            updated_at=utc_now_iso(),
        )
        self._persist_agent_connection(updated)
        return updated

    def delete_agent_connection(self, connection_id: str) -> None:
        """Agent Connection 삭제 (soft delete)"""
        connection = self.get_agent_connection(connection_id)
        connection.deleted_at = utc_now_iso()
        connection.updated_at = connection.deleted_at
        self._persist_agent_connection(connection)

    def reset(self) -> None:
        """모든 Agent Connection 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM agent_connections")
            conn.commit()
        logger.info("AgentConnectionRegistry 초기화 완료")
