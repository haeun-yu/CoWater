from datetime import datetime

from sqlalchemy import (
    ARRAY,
    DateTime,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class ReportModel(Base):
    """보고서 저장 (flow 단위의 일련된 이벤트에 대한 AI 분석 보고서)"""

    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    flow_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    alert_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    report_type: Mapped[str] = mapped_column(
        Text, server_default="summary"
    )  # "summary" | "detailed" | "incident"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    ai_model: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
