from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any
from uuid import uuid4

from src.core.models import AgentRecord
from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_AGENTS_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


class AgentRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/agents.db"

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
                conn.execute(_CREATE_AGENTS_SQL)
                conn.commit()
            logger.info(f"AgentRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"AgentRegistry DB 초기화 실패: {e}")

    def _row_to_agent(self, row: sqlite3.Row) -> AgentRecord:
        data = json.loads(row["data"])
        data.setdefault("agent_id", row["agent_id"])
        data.setdefault("created_at", row["created_at"])
        data.setdefault("updated_at", row["updated_at"])
        return AgentRecord(**data)

    def _persist_agent(self, agent: AgentRecord) -> None:
        data = agent.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agents (agent_id, data, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (agent.agent_id, json.dumps(data), agent.created_at, agent.updated_at),
            )
            conn.commit()

    def create_agent(
        self,
        name: str,
        type: str,
        role: str,
        endpoint: Dict[str, Any],
        capabilities: List[str],
        device_id: str | None = None,
        gateway_agent_id: str | None = None,
    ) -> AgentRecord:
        """새 에이전트 생성"""
        agent = AgentRecord(
            agent_id=str(uuid4()),
            name=name,
            type=type,
            role=role,
            device_id=device_id,
            endpoint=endpoint,
            capabilities=capabilities,
            gateway_agent_id=gateway_agent_id,
            environment_state="SURFACE",
            active_mediums=capabilities[:],
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        self._persist_agent(agent)
        return agent

    def get_agent(self, agent_id: str) -> AgentRecord:
        """에이전트 조회"""
        with self._connect() as conn:
            row = conn.execute("SELECT agent_id, data, created_at, updated_at FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
            if not row:
                raise KeyError(f"Agent not found: {agent_id}")
            return self._row_to_agent(row)

    def get_agent_by_device_id(self, device_id: str) -> AgentRecord:
        """Device ID로 에이전트 조회"""
        with self._connect() as conn:
            rows = conn.execute("SELECT agent_id, data, created_at, updated_at FROM agents").fetchall()
            for row in rows:
                agent = self._row_to_agent(row)
                if agent.device_id == device_id:
                    return agent
            raise KeyError(f"Agent not found for device: {device_id}")

    def list_agents(self, limit: int = 100, offset: int = 0) -> List[AgentRecord]:
        """에이전트 목록 조회"""
        query = "SELECT agent_id, data, created_at, updated_at FROM agents ORDER BY created_at DESC"
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
            return [self._row_to_agent(row) for row in rows]

    def list_agents_by_type(self, agent_type: str) -> List[AgentRecord]:
        """타입별 에이전트 목록 조회"""
        agents = []
        with self._connect() as conn:
            rows = conn.execute("SELECT agent_id, data, created_at, updated_at FROM agents").fetchall()
            for row in rows:
                agent = self._row_to_agent(row)
                if agent.type == agent_type:
                    agents.append(agent)
        return agents

    def update_agent(self, agent_id: str, **kwargs) -> AgentRecord:
        """에이전트 정보 업데이트"""
        agent = self.get_agent(agent_id)
        for key, value in kwargs.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
        agent.updated_at = utc_now_iso()
        self._persist_agent(agent)
        return agent

    def update_agent_heartbeat(self, agent_id: str) -> AgentRecord:
        """에이전트 heartbeat 업데이트"""
        agent = self.get_agent(agent_id)
        agent.last_heartbeat_at = utc_now_iso()
        agent.updated_at = utc_now_iso()
        self._persist_agent(agent)
        return agent

    def delete_agent(self, agent_id: str) -> None:
        """에이전트 삭제"""
        agent = self.get_agent(agent_id)
        agent.deleted_at = utc_now_iso()
        self._persist_agent(agent)

    def reset(self) -> None:
        """모든 에이전트 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM agents")
            conn.commit()
        logger.info("AgentRegistry 초기화 완료")
