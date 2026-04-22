"""
UVA (Universal Viz Agent) Data Contract Endpoints
CoWater 데이터를 UVA 형식으로 변환하여 제공
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import PlatformReportModel, AlertModel

router = APIRouter(prefix="/api", tags=["uva"])


# ── UVA Data Contract Models ───────────────────────────────────────────────


class Position(BaseModel):
    latitude: float
    longitude: float
    altitude: Optional[float] = None


class Entity(BaseModel):
    """움직이는 객체 (vessel, drone, buoy 등)"""
    id: str
    type: str  # vessel, drone, buoy, etc
    label: str
    position: Position
    heading: Optional[float] = None  # degrees
    speed: Optional[float] = None  # knots
    state: Optional[str] = None
    metadata: Optional[dict] = None
    trail: Optional[list[list[float]]] = None  # [[lat, lon], ...]
    timestamp: datetime


class Event(BaseModel):
    """발생한 사건 (alert)"""
    id: str
    entity_id: str
    event_type: str  # collision, anomaly, zone_violation, etc
    severity: str  # info, warning, critical
    message: str
    timestamp: datetime
    details: Optional[dict] = None
    status: Optional[str] = None  # active, resolved


class Area(BaseModel):
    """지도에 그릴 영역 (zone)"""
    id: str
    name: str
    geometry: dict  # GeoJSON
    type: Optional[str] = None  # restricted, danger, info
    style: Optional[dict] = None


class EntitiesResponse(BaseModel):
    entities: list[Entity]
    timestamp: datetime


class EventsResponse(BaseModel):
    events: list[Event]
    timestamp: datetime


class AreasResponse(BaseModel):
    areas: list[Area]
    timestamp: datetime


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/entities", response_model=EntitiesResponse)
async def get_entities(db: AsyncSession = Depends(get_db)):
    """
    최신 플랫폼 위치 데이터를 Entity 형식으로 반환
    """
    # 각 플랫폼의 최신 리포트만 조회
    query = select(PlatformReportModel).order_by(
        PlatformReportModel.platform_id,
        PlatformReportModel.time.desc()
    )
    result = await db.execute(query)
    reports = result.scalars().all()

    # platform_id별 최신 데이터만 추출
    latest_by_platform = {}
    for report in reports:
        if report.platform_id not in latest_by_platform:
            latest_by_platform[report.platform_id] = report

    entities = []
    for report in latest_by_platform.values():
        entity = Entity(
            id=report.platform_id,
            type=report.source_protocol or "unknown",
            label=report.platform_id,
            position=Position(
                latitude=report.lat,
                longitude=report.lon,
                altitude=report.altitude_m
            ),
            heading=report.heading,
            speed=report.sog,
            state=report.nav_status,
            metadata={},
            timestamp=report.time
        )
        entities.append(entity)

    return EntitiesResponse(
        entities=entities,
        timestamp=datetime.utcnow()
    )


@router.get("/events", response_model=EventsResponse)
async def get_events(db: AsyncSession = Depends(get_db)):
    """
    활성 경보를 Event 형식으로 반환
    """
    query = select(AlertModel).where(
        AlertModel.status == "active"
    ).order_by(AlertModel.created_at.desc()).limit(100)

    result = await db.execute(query)
    alerts = result.scalars().all()

    events = []
    for alert in alerts:
        event = Event(
            id=alert.alert_id,
            entity_id=(alert.platform_ids[0] if alert.platform_ids else "unknown"),
            event_type=alert.alert_type or "generic",
            severity=alert.severity or "info",
            message=alert.message,
            timestamp=alert.created_at,
            details=alert.metadata_ or {},
            status=alert.status
        )
        events.append(event)

    return EventsResponse(
        events=events,
        timestamp=datetime.utcnow()
    )


@router.get("/areas", response_model=AreasResponse)
async def get_areas(db: AsyncSession = Depends(get_db)):
    """
    관제 구역을 Area 형식으로 반환
    """
    # 현재는 빈 응답 (zones 테이블 구조 확인 후 구현)
    return AreasResponse(
        areas=[],
        timestamp=datetime.utcnow()
    )
