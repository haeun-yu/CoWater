import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import ReportModel

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


class ReportsListResponse(BaseModel):
    reports: list[ReportResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


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
    query = select(ReportModel)

    if flow_id:
        query = query.where(ReportModel.flow_id == flow_id)
    if report_type:
        query = query.where(ReportModel.report_type == report_type)

    # 전체 개수 조회
    count_result = await db.execute(
        select(func.count()).select_from(ReportModel).where(
            (ReportModel.flow_id == flow_id) if flow_id else True
        ).where(
            (ReportModel.report_type == report_type) if report_type else True
        )
    )
    total = count_result.scalar() or 0

    # 최신순 정렬 + 페이지네이션
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
