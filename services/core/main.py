import asyncio
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.platforms import router as platforms_router
from api.alerts import router as alerts_router
from api.ws import router as ws_router
from redis_client import get_redis, close_redis
from services.track_consumer import consume_platform_reports
from services.alert_consumer import consume_alerts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = await get_redis()

    # Redis 구독 Consumer를 백그라운드 태스크로 실행
    task_track = asyncio.create_task(consume_platform_reports(redis))
    task_alert = asyncio.create_task(consume_alerts(redis))
    logger.info("CoWater Core Backend started")

    yield

    task_track.cancel()
    task_alert.cancel()
    await close_redis()
    logger.info("CoWater Core Backend stopped")


app = FastAPI(
    title="CoWater Core API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(platforms_router)
app.include_router(alerts_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
