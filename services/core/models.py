from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class PlatformModel(Base):
    __tablename__ = "platforms"

    platform_id: Mapped[str] = mapped_column(Text, primary_key=True)
    platform_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    flag: Mapped[str | None] = mapped_column(Text)
    source_protocol: Mapped[str] = mapped_column(Text, nullable=False)
    moth_channel: Mapped[str | None] = mapped_column(Text)
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    dimensions: Mapped[dict | None] = mapped_column(JSONB)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


class PlatformReportModel(Base):
    __tablename__ = "platform_reports"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    platform_id: Mapped[str] = mapped_column(Text, primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    depth_m: Mapped[float | None] = mapped_column(Float)
    altitude_m: Mapped[float | None] = mapped_column(Float)
    sog: Mapped[float | None] = mapped_column(Float)
    cog: Mapped[float | None] = mapped_column(Float)
    heading: Mapped[float | None] = mapped_column(Float)
    rot: Mapped[float | None] = mapped_column(Float)
    nav_status: Mapped[str | None] = mapped_column(Text)
    source_protocol: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[bytes | None] = mapped_column(LargeBinary)


class ZoneModel(Base):
    __tablename__ = "zones"

    zone_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    zone_type: Mapped[str] = mapped_column(Text, nullable=False)
    geometry: Mapped[object] = mapped_column(Geometry("GEOMETRY", srid=4326), nullable=False)
    rules: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))


class AlertModel(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default=text("'new'"))
    platform_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    zone_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    generated_by: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    # dedup_key: 전용 컬럼으로 인덱스 지원 (JSONB metadata에서 추출하는 것보다 빠름)
    dedup_key: Mapped[str | None] = mapped_column(Text, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("NOW()"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
