from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List
from uuid import uuid4

from src.core.models import ReportRecord
from src.registry.registry_utils import utc_now_iso

logger = logging.getLogger(__name__)

_CREATE_REPORTS_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


class ReportRegistry:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or ".data/reports.db"

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
                conn.execute(_CREATE_REPORTS_SQL)
                conn.commit()
            logger.info(f"ReportRegistry DB 초기화: {self._db_path}")
        except Exception as e:
            logger.error(f"ReportRegistry DB 초기화 실패: {e}")

    def _row_to_report(self, row: sqlite3.Row) -> ReportRecord:
        data = json.loads(row["data"])
        data.setdefault("report_id", row["report_id"])
        data.setdefault("created_at", row["created_at"])
        return ReportRecord(**data)

    def _persist_report(self, report: ReportRecord) -> None:
        data = report.to_dict()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO reports (report_id, data, created_at) VALUES (?, ?, ?)",
                (report.report_id, json.dumps(data), report.created_at),
            )
            conn.commit()

    def create_report(
        self,
        type: str,
        target_type: str,
        target_id: str,
        title: str,
        summary: str,
        details: dict | None = None,
        created_by: dict | None = None,
    ) -> ReportRecord:
        """새 Report 생성"""
        report = ReportRecord(
            report_id=str(uuid4()),
            type=type,
            target_type=target_type,
            target_id=target_id,
            title=title,
            summary=summary,
            details=details or {},
            created_by=created_by or {"type": "SYSTEM", "id": "system"},
            created_at=utc_now_iso(),
        )
        self._persist_report(report)
        return report

    def get_report(self, report_id: str) -> ReportRecord:
        """Report 조회"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_id, data, created_at FROM reports WHERE report_id = ?",
                (report_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Report not found: {report_id}")
            return self._row_to_report(row)

    def list_reports(self, limit: int = 100, offset: int = 0) -> List[ReportRecord]:
        """Report 목록 조회"""
        query = "SELECT report_id, data, created_at FROM reports ORDER BY created_at DESC"
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
            return [self._row_to_report(row) for row in rows]

    def list_reports_by_target(self, target_type: str, target_id: str) -> List[ReportRecord]:
        """대상별 Report 목록 조회"""
        reports = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT report_id, data, created_at FROM reports ORDER BY created_at DESC"
            ).fetchall()
            for row in rows:
                report = self._row_to_report(row)
                if report.target_type == target_type and report.target_id == target_id:
                    reports.append(report)
        return reports

    def reset(self) -> None:
        """모든 Report 삭제 (테스트용)"""
        with self._connect() as conn:
            conn.execute("DELETE FROM reports")
            conn.commit()
        logger.info("ReportRegistry 초기화 완료")
