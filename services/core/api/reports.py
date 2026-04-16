import logging
from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import ReportModel
from ws_hub import hub

router = APIRouter(prefix="/reports", tags=["reports"])
logger = logging.getLogger(__name__)


class ReportResponse(BaseModel):
    report_id: str
    flow_id: str
    alert_ids: list[str]
    report_type: str
    content: str
    summary: str | None
    ai_model: str
    metadata: dict
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, m: ReportModel) -> "ReportResponse":
        return cls(
            report_id=m.report_id,
            flow_id=m.flow_id,
            alert_ids=m.alert_ids or [],
            report_type=m.report_type,
            content=m.content,
            summary=m.summary,
            ai_model=m.ai_model,
            metadata=m.metadata_ or {},
            created_at=m.created_at,
        )


class CreateReportRequest(BaseModel):
    """리포트 생성 요청 (report-agents에서 호출)"""
    flow_id: str
    alert_ids: list[str]
    report_type: str
    content: str
    ai_model: str
    summary: str | None = None
    metadata: dict | None = None


class CreateReportResponse(BaseModel):
    """리포트 생성 응답"""
    report_id: str
    status: str


class ReportsListResponse(BaseModel):
    reports: list[ReportResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.post("", status_code=201, response_model=CreateReportResponse)
async def create_report(
    req: CreateReportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateReportResponse:
    """
    리포트 생성 및 저장 (Core만 DB 접근)

    report-agents에서 호출하여 리포트를 생성하고 저장합니다.
    """
    report_id = str(uuid4())

    try:
        # DB에 리포트 저장
        stmt = insert(ReportModel).values(
            report_id=report_id,
            flow_id=req.flow_id,
            alert_ids=req.alert_ids,
            report_type=req.report_type,
            content=req.content,
            summary=req.summary,
            ai_model=req.ai_model,
            metadata_=req.metadata or {},
        )
        await db.execute(stmt)
        await db.commit()

        # WebSocket 브로드캐스트 (프론트엔드 실시간 업데이트)
        await hub.broadcast("reports", {
            "report_id": report_id,
            "flow_id": req.flow_id,
            "alert_ids": req.alert_ids,
            "report_type": req.report_type,
            "ai_model": req.ai_model,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        logger.info("Report created: %s (type=%s)", report_id, req.report_type)

        return CreateReportResponse(
            report_id=report_id,
            status="created"
        )

    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to create report: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create report")


@router.get("", response_model=ReportsListResponse)
async def list_reports(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    flow_id: Optional[str] = Query(None),
    report_type: Optional[str] = Query(None),
) -> ReportsListResponse:
    """
    보고서 목록 조회 (페이지네이션)

    Query Parameters:
    - page: 페이지 번호 (기본값: 1)
    - page_size: 페이지 크기 (기본값: 10, 최대: 100)
    - flow_id: flow_id로 필터 (선택)
    - report_type: report_type으로 필터 (선택: summary, detailed, incident)
    """
    # Build query with filters
    query = select(ReportModel)
    if flow_id:
        query = query.where(ReportModel.flow_id == flow_id)
    if report_type:
        query = query.where(ReportModel.report_type == report_type)

    # Get total count using same filter conditions
    count_query = select(func.count()).select_from(ReportModel)
    if flow_id:
        count_query = count_query.where(ReportModel.flow_id == flow_id)
    if report_type:
        count_query = count_query.where(ReportModel.report_type == report_type)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(desc(ReportModel.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    reports = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ReportsListResponse(
        reports=[ReportResponse.from_model(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReportResponse:
    """
    보고서 상세 조회
    """
    query = select(ReportModel).where(ReportModel.report_id == report_id)
    result = await db.execute(query)
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    return ReportResponse.from_model(report)
