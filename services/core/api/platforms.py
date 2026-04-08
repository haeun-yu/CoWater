from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text
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


class SpatialReferencePoint(BaseModel):
    time: datetime
    lat: float
    lon: float


class NearbyPlatform(BaseModel):
    platform_id: str
    platform_type: str
    name: str
    lat: float
    lon: float
    sog: float | None
    cog: float | None
    heading: float | None
    nav_status: str | None
    distance_nm: float


class NearbyZone(BaseModel):
    zone_id: str
    name: str
    zone_type: str
    active: bool
    contains_platform: bool
    distance_nm: float
    rules: dict


class PlatformSpatialContext(BaseModel):
    platform_id: str
    reference: SpatialReferencePoint
    nearby_platforms: list[NearbyPlatform]
    nearby_zones: list[NearbyZone]
    nearest_fairway: NearbyZone | None
    route_deviation_nm: float | None
    in_fairway: bool


class ZoneDwellSession(BaseModel):
    zone_id: str
    zone_name: str
    zone_type: str | None
    entered_at: datetime
    exited_at: datetime | None
    dwell_minutes: float | None
    active: bool


class PlatformZoneDwell(BaseModel):
    platform_id: str
    active_sessions: list[ZoneDwellSession]
    recent_sessions: list[ZoneDwellSession]


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


@router.get("/{platform_id}/spatial-context", response_model=PlatformSpatialContext)
async def get_spatial_context(
    platform_id: str,
    radius_nm: float = Query(default=5.0, ge=0.5, le=50.0),
    zone_limit: int = Query(default=8, ge=1, le=20),
    platform_limit: int = Query(default=8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    latest_stmt = text(
        """
        SELECT time, lat, lon
        FROM platform_reports
        WHERE platform_id = :platform_id
        ORDER BY time DESC
        LIMIT 1
        """
    )
    latest_row = (
        (await db.execute(latest_stmt, {"platform_id": platform_id})).mappings().first()
    )
    if latest_row is None:
        raise HTTPException(
            404, f"No position history found for platform '{platform_id}'"
        )

    radius_m = radius_nm * 1852.0
    params = {
        "platform_id": platform_id,
        "lat": latest_row["lat"],
        "lon": latest_row["lon"],
        "radius_m": radius_m,
        "zone_limit": zone_limit,
        "platform_limit": platform_limit,
    }

    nearby_platforms_stmt = text(
        """
        WITH latest_reports AS (
            SELECT DISTINCT ON (pr.platform_id)
                pr.platform_id,
                pr.time,
                pr.lat,
                pr.lon,
                pr.sog,
                pr.cog,
                pr.heading,
                pr.nav_status
            FROM platform_reports pr
            ORDER BY pr.platform_id, pr.time DESC
        ), reference AS (
            SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS ref_geog
        )
        SELECT
            lr.platform_id,
            p.platform_type,
            p.name,
            lr.lat,
            lr.lon,
            lr.sog,
            lr.cog,
            lr.heading,
            lr.nav_status,
            ST_Distance(
                ST_SetSRID(ST_MakePoint(lr.lon, lr.lat), 4326)::geography,
                reference.ref_geog
            ) / 1852.0 AS distance_nm
        FROM latest_reports lr
        JOIN platforms p ON p.platform_id = lr.platform_id
        CROSS JOIN reference
        WHERE lr.platform_id <> :platform_id
          AND ST_DWithin(
                ST_SetSRID(ST_MakePoint(lr.lon, lr.lat), 4326)::geography,
                reference.ref_geog,
                :radius_m
          )
        ORDER BY distance_nm ASC
        LIMIT :platform_limit
        """
    )

    nearby_zones_stmt = text(
        """
        WITH reference AS (
            SELECT
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS ref_geom,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS ref_geog
        )
        SELECT
            z.zone_id::text AS zone_id,
            z.name,
            z.zone_type,
            z.active,
            ST_Intersects(z.geometry, reference.ref_geom) AS contains_platform,
            ST_Distance(z.geometry::geography, reference.ref_geog) / 1852.0 AS distance_nm,
            z.rules
        FROM zones z
        CROSS JOIN reference
        WHERE z.active = TRUE
          AND (
                ST_Intersects(z.geometry, reference.ref_geom)
                OR ST_DWithin(z.geometry::geography, reference.ref_geog, :radius_m)
          )
        ORDER BY contains_platform DESC, distance_nm ASC, z.name ASC
        LIMIT :zone_limit
        """
    )

    nearest_fairway_stmt = text(
        """
        WITH reference AS (
            SELECT
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS ref_geom,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS ref_geog
        )
        SELECT
            z.zone_id::text AS zone_id,
            z.name,
            z.zone_type,
            z.active,
            ST_Intersects(z.geometry, reference.ref_geom) AS contains_platform,
            ST_Distance(z.geometry::geography, reference.ref_geog) / 1852.0 AS distance_nm,
            z.rules
        FROM zones z
        CROSS JOIN reference
        WHERE z.active = TRUE
          AND z.zone_type IN ('fairway', 'tss', 'precautionary')
        ORDER BY contains_platform DESC, distance_nm ASC, z.name ASC
        LIMIT 1
        """
    )

    nearby_platform_rows = (
        (await db.execute(nearby_platforms_stmt, params)).mappings().all()
    )
    nearby_zone_rows = (await db.execute(nearby_zones_stmt, params)).mappings().all()
    nearest_fairway_row = (
        (await db.execute(nearest_fairway_stmt, params)).mappings().first()
    )

    nearby_platforms = [
        NearbyPlatform(
            platform_id=row["platform_id"],
            platform_type=row["platform_type"],
            name=row["name"],
            lat=row["lat"],
            lon=row["lon"],
            sog=row["sog"],
            cog=row["cog"],
            heading=row["heading"],
            nav_status=row["nav_status"],
            distance_nm=round(float(row["distance_nm"]), 3),
        )
        for row in nearby_platform_rows
    ]

    nearby_zones = [
        NearbyZone(
            zone_id=row["zone_id"],
            name=row["name"],
            zone_type=row["zone_type"],
            active=row["active"],
            contains_platform=row["contains_platform"],
            distance_nm=round(float(row["distance_nm"]), 3),
            rules=row["rules"] or {},
        )
        for row in nearby_zone_rows
    ]

    nearest_fairway = None
    if nearest_fairway_row is not None:
        nearest_fairway = NearbyZone(
            zone_id=nearest_fairway_row["zone_id"],
            name=nearest_fairway_row["name"],
            zone_type=nearest_fairway_row["zone_type"],
            active=nearest_fairway_row["active"],
            contains_platform=nearest_fairway_row["contains_platform"],
            distance_nm=round(float(nearest_fairway_row["distance_nm"]), 3),
            rules=nearest_fairway_row["rules"] or {},
        )

    in_fairway = bool(nearest_fairway.contains_platform) if nearest_fairway else False
    route_deviation_nm = (
        0.0
        if in_fairway
        else (nearest_fairway.distance_nm if nearest_fairway else None)
    )

    return PlatformSpatialContext(
        platform_id=platform_id,
        reference=SpatialReferencePoint(
            time=latest_row["time"],
            lat=latest_row["lat"],
            lon=latest_row["lon"],
        ),
        nearby_platforms=nearby_platforms,
        nearby_zones=nearby_zones,
        nearest_fairway=nearest_fairway,
        route_deviation_nm=route_deviation_nm,
        in_fairway=in_fairway,
    )


@router.get("/{platform_id}/zone-dwell", response_model=PlatformZoneDwell)
async def get_zone_dwell(
    platform_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    stmt = text(
        """
        SELECT
            a.alert_type,
            a.zone_id::text AS zone_id,
            a.created_at,
            z.name AS zone_name,
            z.zone_type
        FROM alerts a
        LEFT JOIN zones z ON z.zone_id = a.zone_id
        WHERE :platform_id = ANY(a.platform_ids)
          AND a.zone_id IS NOT NULL
          AND a.alert_type IN ('zone_intrusion', 'zone_exit')
        ORDER BY a.created_at ASC
        """
    )
    rows = (await db.execute(stmt, {"platform_id": platform_id})).mappings().all()

    active_entries: dict[str, dict] = {}
    sessions: list[ZoneDwellSession] = []

    for row in rows:
        zone_id = row["zone_id"]
        if row["alert_type"] == "zone_intrusion":
            active_entries[zone_id] = {
                "zone_name": row["zone_name"] or zone_id,
                "zone_type": row["zone_type"],
                "entered_at": row["created_at"],
            }
            continue

        entry = active_entries.pop(zone_id, None)
        if entry is None:
            continue

        dwell_minutes = (row["created_at"] - entry["entered_at"]).total_seconds() / 60.0
        sessions.append(
            ZoneDwellSession(
                zone_id=zone_id,
                zone_name=entry["zone_name"],
                zone_type=entry["zone_type"],
                entered_at=entry["entered_at"],
                exited_at=row["created_at"],
                dwell_minutes=round(dwell_minutes, 1),
                active=False,
            )
        )

    active_sessions = [
        ZoneDwellSession(
            zone_id=zone_id,
            zone_name=entry["zone_name"],
            zone_type=entry["zone_type"],
            entered_at=entry["entered_at"],
            exited_at=None,
            dwell_minutes=round(
                (
                    datetime.now(entry["entered_at"].tzinfo) - entry["entered_at"]
                ).total_seconds()
                / 60.0,
                1,
            ),
            active=True,
        )
        for zone_id, entry in active_entries.items()
    ]

    recent_sessions = sorted(sessions, key=lambda item: item.entered_at, reverse=True)[
        :limit
    ]
    active_sessions = sorted(
        active_sessions, key=lambda item: item.entered_at, reverse=True
    )

    return PlatformZoneDwell(
        platform_id=platform_id,
        active_sessions=active_sessions,
        recent_sessions=recent_sessions,
    )
