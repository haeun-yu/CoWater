from __future__ import annotations

"""알림 대응 기록."""

from typing import Any

from ..core.config import utc_now_iso


def record_response(hub: Any, response: Any) -> Any:
    hub.state.responses.append(response)
    hub.state.responses = hub.state.responses[-hub.notification_settings.get("retain", 100):]
    hub.state.remember({"kind": "system.response", "at": utc_now_iso(), "response": response.to_dict()})
    return response
