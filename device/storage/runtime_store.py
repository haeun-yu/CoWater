from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RuntimeStore:
    def __init__(self, snapshot_path: str | Path) -> None:
        self.snapshot_path = Path(snapshot_path)
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def load_snapshot(self, instance_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                if not self.snapshot_path.exists():
                    return {}
                payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    snapshot = payload.get(instance_id)
                    if isinstance(snapshot, dict):
                        return dict(snapshot.get("snapshot") or {})
                return {}
            except Exception as exc:
                logger.warning("RuntimeStore snapshot load failed (instance_id=%s): %s", instance_id, exc)
                return {}

    def save_snapshot(self, instance_id: str, snapshot: dict[str, Any], updated_at: str) -> None:
        with self._lock:
            try:
                payload: dict[str, Any] = {}
                if self.snapshot_path.exists():
                    existing = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
                    if isinstance(existing, dict):
                        payload = existing
                payload[instance_id] = {
                    "updated_at": updated_at,
                    "snapshot": snapshot,
                }
                tmp_path = self.snapshot_path.with_suffix(self.snapshot_path.suffix + ".tmp")
                tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
                tmp_path.replace(self.snapshot_path)
            except Exception as exc:
                logger.error("RuntimeStore snapshot save failed (instance_id=%s): %s", instance_id, exc)
