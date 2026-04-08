from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import PlatformModel, PlatformReportModel
from services.track_consumer import clear_platform_cache

router = APIRouter(prefix="/platforms", tags=["platforms"])


# ── Request / Response schemas ──────────────────────────────────────────────


class PlatformCreate(BaseModel):
    platform_id: str
    platform_type: str
    name: str
    source_protocol: str
    flag: str | None = None
    moth_channel: str | None = None
    capabilities: list[str] = []
    dimensions: dict | None = None
    metadata: dict = {}


class PlatformResponse(BaseModel):
    platform_id: str
    platform_type: str
    name: str
    source_protocol: str
    flag: str | None
    moth_channel: str | None
    capabilities: list[str]
    dimensions: dict | None
    metadata: dict
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m: "PlatformModel") -> "PlatformResponse":
        return cls(
            platform_id=m.platform_id,
            platform_type=m.platform_type,
            name=m.name,
            source_protocol=m.source_protocol,
            flag=m.flag,
            moth_channel=m.moth_channel,
            capabilities=m.capabilities or [],
            dimensions=m.dimensions,
            metadata=m.metadata_ or {},
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class TrackPoint(BaseModel):
    time: datetime
    lat: float
    lon: float
    sog: float | None
    cog: float | None
    heading: float | None
    nav_status: str | None


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=list[PlatformResponse])
async def list_platforms(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(PlatformModel))
    return [PlatformResponse.from_model(r) for r in result.scalars().all()]


@router.get("/{platform_id}", response_model=PlatformResponse)
async def get_platform(platform_id: str, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await db.get(PlatformModel, platform_id)
    if row is None:
        raise HTTPException(404, f"Platform '{platform_id}' not found")
    return PlatformResponse.from_model(row)


@router.post("", response_model=PlatformResponse, status_code=201)
async def create_platform(
    body: PlatformCreate, db: Annotated[AsyncSession, Depends(get_db)]
):
    platform = PlatformModel(
        platform_id=body.platform_id,
        platform_type=body.platform_type,
        name=body.name,
        source_protocol=body.source_protocol,
        flag=body.flag,
        moth_channel=body.moth_channel,
        capabilities=body.capabilities,
        dimensions=body.dimensions,
        metadata_=body.metadata,
    )
    db.add(platform)
    await db.commit()
    await db.refresh(platform)
    return PlatformResponse.from_model(platform)


@router.patch("/{platform_id}", response_model=PlatformResponse)
async def update_platform(
    platform_id: str,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from datetime import timezone

    row = await db.get(PlatformModel, platform_id)
    if row is None:
        raise HTTPException(404, f"Platform '{platform_id}' not found")
    allowed = {"name", "flag", "moth_channel", "capabilities", "dimensions"}
    for k, v in body.items():
        if k in allowed:
            setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    clear_platform_cache(platform_id)
    return PlatformResponse.from_model(row)


@router.get("/{platform_id}/track", response_model=list[TrackPoint])
async def get_track(
    platform_id: str,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
):
    # 시간 범위 조건을 먼저 적용한 뒤 최신 N개를 역순으로 가져와 다시 정렬
    # — limit을 "최근 N개"로 유지하면서 프론트 항적 렌더링은 오름차순(오래된→최신)으로 보장
    inner = (
        select(PlatformReportModel)
        .where(PlatformReportModel.platform_id == platform_id)
        .order_by(PlatformReportModel.time.desc())
        .limit(limit)
    )
    if from_:
        inner = inner.where(PlatformReportModel.time >= from_)
    if to:
        inner = inner.where(PlatformReportModel.time <= to)

    subq = inner.subquery()
    stmt = select(subq).order_by(subq.c.time.asc())

    result = await db.execute(stmt)
    rows = result.all()
    return [
        TrackPoint(
            time=r.time,
            lat=r.lat,
            lon=r.lon,
            sog=r.sog,
            cog=r.cog,
            heading=r.heading,
            nav_status=r.nav_status,
        )
        for r in rows
    ]
