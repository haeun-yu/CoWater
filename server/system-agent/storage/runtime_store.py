from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


_MISSING = object()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _loads(raw: str | bytes | None) -> dict[str, Any]:
    if not raw:
        return {}
    return json.loads(raw)


class RuntimeStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_kv (
                    collection TEXT NOT NULL,
                    item_key TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (collection, item_key)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_log (
                    collection TEXT NOT NULL,
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self.conn.commit()

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    def kv_snapshot(self, collection: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            cursor = self.conn.execute(
                "SELECT item_key, data FROM runtime_kv WHERE collection = ? ORDER BY created_at, item_key",
                (collection,),
            )
            return {str(row["item_key"]): _loads(row["data"]) for row in cursor.fetchall()}

    def kv_get(self, collection: str, item_key: str) -> dict[str, Any]:
        with self._lock:
            row = self.conn.execute(
                "SELECT data FROM runtime_kv WHERE collection = ? AND item_key = ?",
                (collection, str(item_key)),
            ).fetchone()
        if row is None:
            raise KeyError(item_key)
        return _loads(row["data"])

    def kv_set(self, collection: str, item_key: str, data: dict[str, Any]) -> None:
        with self._lock:
            now = utc_now()
            current = self.conn.execute(
                "SELECT created_at FROM runtime_kv WHERE collection = ? AND item_key = ?",
                (collection, str(item_key)),
            ).fetchone()
            created_at = current["created_at"] if current else now
            self.conn.execute(
                """
                INSERT OR REPLACE INTO runtime_kv (collection, item_key, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (collection, str(item_key), _dumps(data), created_at, now),
            )
            self.conn.commit()

    def kv_delete(self, collection: str, item_key: str) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM runtime_kv WHERE collection = ? AND item_key = ?",
                (collection, str(item_key)),
            )
            self.conn.commit()

    def kv_clear(self, collection: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM runtime_kv WHERE collection = ?", (collection,))
            self.conn.commit()

    def log_snapshot(self, collection: str, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if limit is None:
                cursor = self.conn.execute(
                    "SELECT data FROM runtime_log WHERE collection = ? ORDER BY item_id",
                    (collection,),
                )
                return [_loads(row["data"]) for row in cursor.fetchall()]
            cursor = self.conn.execute(
                "SELECT data FROM runtime_log WHERE collection = ? ORDER BY item_id DESC LIMIT ?",
                (collection, limit),
            )
            rows = cursor.fetchall()
            return [_loads(row["data"]) for row in reversed(rows)]

    def log_append(self, collection: str, data: dict[str, Any], *, keep_last_n: int | None = None) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO runtime_log (collection, data, created_at) VALUES (?, ?, ?)",
                (collection, _dumps(data), utc_now()),
            )
            self.conn.commit()
            if keep_last_n is not None and keep_last_n >= 0:
                self.log_trim(collection, keep_last_n)

    def log_count(self, collection: str) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM runtime_log WHERE collection = ?", (collection,)).fetchone()
            return int(row["count"] if row else 0)

    def log_trim(self, collection: str, keep_last_n: int) -> None:
        if keep_last_n < 0:
            return
        with self._lock:
            self.conn.execute(
                """
                DELETE FROM runtime_log
                WHERE item_id IN (
                    SELECT item_id FROM runtime_log
                    WHERE collection = ?
                    ORDER BY item_id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (collection, keep_last_n),
            )
            self.conn.commit()

    def log_clear(self, collection: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM runtime_log WHERE collection = ?", (collection,))
            self.conn.commit()


@dataclass
class PersistentMapping(MutableMapping[str, dict[str, Any]]):
    store: RuntimeStore
    collection: str
    key_encoder: Callable[[Any], str] = str
    key_decoder: Callable[[str], Any] = str

    def __getitem__(self, key: Any) -> dict[str, Any]:
        return self.store.kv_get(self.collection, self.key_encoder(key))

    def __setitem__(self, key: Any, value: dict[str, Any]) -> None:
        self.store.kv_set(self.collection, self.key_encoder(key), value)

    def __delitem__(self, key: Any) -> None:
        self.store.kv_delete(self.collection, self.key_encoder(key))

    def __iter__(self) -> Iterator[Any]:
        for key in self.store.kv_snapshot(self.collection).keys():
            yield self.key_decoder(key)

    def __len__(self) -> int:
        return len(self.store.kv_snapshot(self.collection))

    def snapshot(self) -> dict[Any, dict[str, Any]]:
        data = self.store.kv_snapshot(self.collection)
        return {self.key_decoder(key): value for key, value in data.items()}

    def values(self) -> list[dict[str, Any]]:  # type: ignore[override]
        return list(self.snapshot().values())

    def items(self) -> list[tuple[Any, dict[str, Any]]]:  # type: ignore[override]
        return list(self.snapshot().items())

    def keys(self) -> list[Any]:  # type: ignore[override]
        return list(self.snapshot().keys())

    def pop(self, key: Any, default: Any = _MISSING) -> Any:
        try:
            value = self[key]
        except KeyError:
            if default is not _MISSING:
                return default
            raise
        self.__delitem__(key)
        return value

    def setdefault(self, key: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            return self[key]
        except KeyError:
            value = default or {}
            self[key] = value
            return self[key]

    def clear(self) -> None:  # type: ignore[override]
        self.store.kv_clear(self.collection)


class PersistentLog:
    def __init__(self, store: RuntimeStore, collection: str, *, keep_last_n: int) -> None:
        self.store = store
        self.collection = collection
        self.keep_last_n = keep_last_n

    def append(self, item: dict[str, Any]) -> None:
        self.store.log_append(self.collection, item, keep_last_n=self.keep_last_n)

    def extend(self, items: Iterable[dict[str, Any]]) -> None:
        for item in items:
            self.append(item)

    def snapshot(self, limit: int | None = None) -> list[dict[str, Any]]:
        return self.store.log_snapshot(self.collection, limit=limit)

    def trim(self, keep_last_n: int) -> None:
        self.store.log_trim(self.collection, keep_last_n)

    def clear(self) -> None:
        self.store.log_clear(self.collection)

    def __len__(self) -> int:
        return self.store.log_count(self.collection)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.store.log_snapshot(self.collection))

    def __getitem__(self, index: int | slice) -> Any:
        items = self.store.log_snapshot(self.collection)
        return items[index]
