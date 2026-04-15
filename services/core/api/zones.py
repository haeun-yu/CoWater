from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import to_shape
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import ProgrammingError
import logging

from db import get_db
from models import ZoneModel

router = APIRouter(prefix="/zones", tags=["zones"])
logger = logging.getLogger(__name__)


class ZoneResponse(BaseModel):
    zone_id: str
    name: str
    zone_type: str
    geometry: dict        # GeoJSON
    rules: dict
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, m: ZoneModel) -> "ZoneResponse":
        # geoalchemy2 geometry → GeoJSON dict 변환
        shape = to_shape(m.geometry)
        import json
        from shapely.geometry import mapping
        geojson = json.loads(json.dumps(mapping(shape)))
        return cls(
            zone_id=m.zone_id,
            name=m.name,
            zone_type=m.zone_type,
            geometry=geojson,
            rules=m.rules or {},
            active=m.active,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )


class ZoneCreate(BaseModel):
    name: str
    zone_type: str
    geometry: dict        # GeoJSON Polygon or MultiPolygon
    rules: dict = {}


@router.get("", response_model=list[ZoneResponse])
async def list_zones(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ZoneModel)
    if active_only:
        stmt = stmt.where(ZoneModel.active == True)
    try:
        result = await db.execute(stmt)
        return [ZoneResponse.from_model(r) for r in result.scalars().all()]
    except ProgrammingError:
        # Local fallback when PostGIS/schema init is incomplete.
        logger.warning("zones table is not ready yet; returning empty list")
        return []


@router.get("/{zone_id}", response_model=ZoneResponse)
async def get_zone(zone_id: str, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await db.get(ZoneModel, zone_id)
    if row is None:
        raise HTTPException(404, f"Zone '{zone_id}' not found")
    return ZoneResponse.from_model(row)


@router.post("", response_model=ZoneResponse, status_code=201)
async def create_zone(body: ZoneCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    import json
    from geoalchemy2.shape import from_shape
    from shapely.geometry import shape as shapely_shape

    geom = from_shape(shapely_shape(body.geometry), srid=4326)
    zone = ZoneModel(
        name=body.name,
        zone_type=body.zone_type,
        geometry=geom,
        rules=body.rules,
    )
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    return ZoneResponse.from_model(zone)


@router.patch("/{zone_id}/deactivate", response_model=ZoneResponse)
async def deactivate_zone(zone_id: str, db: Annotated[AsyncSession, Depends(get_db)]):
    row = await db.get(ZoneModel, zone_id)
    if row is None:
        raise HTTPException(404)
    row.active = False
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return ZoneResponse.from_model(row)
