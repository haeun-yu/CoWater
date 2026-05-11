"""
TaskIdStore: file-backed processed task history

Device Agent가 처리한 task_id를 기억하여 통신 복구 후 중복 실행을 방지합니다.
SQLite 같은 내부 DB 없이 JSON 스냅샷 파일만 사용합니다.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TaskIdStore:
    """File-backed task_id 처리 이력 저장소"""

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path or ".runtime/processed_tasks.json")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _load_payload(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def _write_payload(self, payload: dict[str, Any]) -> None:
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(self._path)

    def is_processed(self, task_id: str) -> dict[str, Any] | None:
        """이미 처리된 task_id면 기존 결과 반환, 없으면 None"""
        with self._lock:
            try:
                payload = self._load_payload()
                record = payload.get(task_id)
                if isinstance(record, dict):
                    result = record.get("result")
                    return dict(result) if isinstance(result, dict) else result
                return None
            except Exception as e:
                logger.warning(f"TaskIdStore 조회 실패 (task_id={task_id}): {e}")
                return None

    def record(self, task_id: str, result: dict[str, Any]) -> None:
        """처리 완료 후 결과 저장"""
        with self._lock:
            try:
                payload = self._load_payload()
                payload[task_id] = {
                    "result": result,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
                self._write_payload(payload)
            except Exception as e:
                logger.error(f"TaskIdStore 저장 실패 (task_id={task_id}): {e}")

    def cleanup_expired(self, ttl_hours: int = 24) -> None:
        """TTL 이상 된 레코드 정리 (기본 24시간)"""
        with self._lock:
            try:
                payload = self._load_payload()
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)
                filtered = {}
                for task_id, record in payload.items():
                    if not isinstance(record, dict):
                        continue
                    processed_at = record.get("processed_at")
                    if not isinstance(processed_at, str):
                        continue
                    try:
                        parsed = datetime.fromisoformat(processed_at)
                    except Exception:
                        continue
                    if parsed >= cutoff_time:
                        filtered[task_id] = record
                self._write_payload(filtered)
                logger.debug(f"TaskIdStore cleanup: {ttl_hours}시간 이상 된 레코드 정리 완료")
            except Exception as e:
                logger.error(f"TaskIdStore cleanup 실패: {e}")
