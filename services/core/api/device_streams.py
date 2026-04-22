from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

import redis.asyncio as aioredis

from redis_client import get_redis
from services.device_stream_consumer import device_streams_key, latest_stream_key

router = APIRouter(prefix="/device-streams", tags=["device-streams"])


class DeviceStreamRecord(BaseModel):
    envelope: dict
    payload: dict


class DeviceStreamsResponse(BaseModel):
    streams: list[DeviceStreamRecord]


async def redis_dep() -> aioredis.Redis:
    return await get_redis()


@router.get("/latest", response_model=DeviceStreamsResponse)
async def list_latest_device_streams(
    stream: Annotated[str | None, Query()] = None,
    redis: aioredis.Redis = Depends(redis_dep),
) -> DeviceStreamsResponse:
    records: list[DeviceStreamRecord] = []
    device_ids = sorted(await redis.smembers("device_stream:devices"))

    for device_id in device_ids:
        streams = sorted(await redis.smembers(device_streams_key(device_id)))
        for stream_name in streams:
            if stream is not None and stream_name != stream:
                continue
            record = await _load_record(redis, device_id, stream_name)
            if record is not None:
                records.append(record)

    return DeviceStreamsResponse(streams=records)


@router.get("/latest/{device_id}", response_model=DeviceStreamsResponse)
async def get_latest_device_streams(
    device_id: str,
    stream: Annotated[str | None, Query()] = None,
    redis: aioredis.Redis = Depends(redis_dep),
) -> DeviceStreamsResponse:
    records: list[DeviceStreamRecord] = []
    streams = sorted(await redis.smembers(device_streams_key(device_id)))
    for stream_name in streams:
        if stream is not None and stream_name != stream:
            continue
        record = await _load_record(redis, device_id, stream_name)
        if record is not None:
            records.append(record)
    return DeviceStreamsResponse(streams=records)


async def _load_record(
    redis: aioredis.Redis,
    device_id: str,
    stream: str,
) -> DeviceStreamRecord | None:
    raw = await redis.get(latest_stream_key(device_id, stream))
    if raw is None:
        return None
    data = json.loads(raw)
    return DeviceStreamRecord(
        envelope=data.get("envelope") or {},
        payload=data.get("payload") or {},
    )
