from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import PlatformModel, PlatformReportModel

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

    model_config = {"from_attributes": True}


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
    return result.scalars().all()


@router.get("/{platform_id}", response_model=PlatformResponse)
async def get_platform(platform_id: str, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await db.get(PlatformModel, platform_id)
    if row is None:
        raise HTTPException(404, f"Platform '{platform_id}' not found")
    return row


@router.post("", response_model=PlatformResponse, status_code=201)
async def create_platform(body: PlatformCreate, db: Annotated[AsyncSession, Depends(get_db)]):
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
    return platform


@router.patch("/{platform_id}", response_model=PlatformResponse)
async def update_platform(
    platform_id: str,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    row = await db.get(PlatformModel, platform_id)
    if row is None:
        raise HTTPException(404, f"Platform '{platform_id}' not found")
    allowed = {"name", "flag", "moth_channel", "capabilities", "dimensions"}
    for k, v in body.items():
        if k in allowed:
            setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{platform_id}/track", response_model=list[TrackPoint])
async def get_track(
    platform_id: str,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(PlatformReportModel)
        .where(PlatformReportModel.platform_id == platform_id)
        .order_by(PlatformReportModel.time.desc())
        .limit(limit)
    )
    if from_:
        stmt = stmt.where(PlatformReportModel.time >= from_)
    if to:
        stmt = stmt.where(PlatformReportModel.time <= to)

    result = await db.execute(stmt)
    rows = result.scalars().all()
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
