from __future__ import annotations

# 02 에이전트의 최종 command 전송과 전달 결과 기록을 담당하는 Execution Layer다.

from dataclasses import dataclass, field
from typing import Any

from .models import DeviceAgentStateRecord, utc_now_iso


@dataclass
class ExecutionRecord:
    at: str
    source: str
    delivered: bool
    command: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "source": self.source,
            "delivered": self.delivered,
            "command": dict(self.command),
            "error": self.error,
        }


class ExecutionLayer:
    async def execute(
        self,
        session: DeviceAgentStateRecord,
        command: dict[str, Any],
        *,
        source: str = "external",
    ) -> ExecutionRecord:
        record = ExecutionRecord(
            at=utc_now_iso(),
            source=source,
            delivered=False,
            command=dict(command),
        )
        websocket = session.websocket
        if websocket is None:
            record.error = "agent is not connected"
            session.last_execution = record.to_dict()
            session.context["execution"] = record.to_dict()
            session.remember(
                {
                    "kind": "execution",
                    "at": record.at,
                    "execution": record.to_dict(),
                }
            )
            return record

        try:
            await websocket.send_json({"kind": "command", **command})
            record.delivered = True
            session.pending_commands.append(dict(command))
        except Exception as exc:  # pragma: no cover - 네트워크 전송 오류 기록
            record.error = str(exc)

        session.last_execution = record.to_dict()
        session.context["execution"] = record.to_dict()
        session.remember(
            {
                "kind": "execution",
                "at": record.at,
                "execution": record.to_dict(),
            }
        )
        return record
