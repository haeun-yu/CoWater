from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class IdentityStore:
    def __init__(self, root: Path, instance_id: str) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in instance_id)
        self.path = self.root / f"{safe}.json"

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, identity: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(identity, indent=2), encoding="utf-8")

