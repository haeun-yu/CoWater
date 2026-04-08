from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
import uuid

AlertType = Literal[
    "cpa",
    "zone_intrusion",
    "anomaly",
    "ais_off",
    "distress",
    "compliance",
    "traffic",
]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["new", "acknowledged", "resolved"]


@dataclass
class Alert:
    alert_type: AlertType
    severity: AlertSeverity
    generated_by: str  # Agent ID
    message: str
    platform_ids: list[str] = field(default_factory=list)
    zone_id: str | None = None
    recommendation: str | None = None  # AI Agent 권고사항
    metadata: dict = field(default_factory=dict)

    # 자동 생성
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: AlertStatus = "new"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "status": self.status,
            "platform_ids": self.platform_ids,
            "zone_id": self.zone_id,
            "generated_by": self.generated_by,
            "message": self.message,
            "recommendation": self.recommendation,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
