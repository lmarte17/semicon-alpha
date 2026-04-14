from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import GenerateReportRequest


router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(
    limit: int = Query(default=50, ge=1, le=100),
    services: APIServices = Depends(get_services),
) -> list[dict]:
    return services.reports.list_reports(limit=limit)


@router.get("/{report_id}")
def get_report(
    report_id: str,
    services: APIServices = Depends(get_services),
) -> dict:
    try:
        return services.reports.get_report(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/generate")
def generate_report(
    request: GenerateReportRequest,
    services: APIServices = Depends(get_services),
) -> dict:
    try:
        return services.reports.generate_report(
            report_type=request.report_type,
            event_id=request.event_id,
            entity_id=request.entity_id,
            compare_entity_id=request.compare_entity_id,
            board_id=request.board_id,
            scenario_id=request.scenario_id,
            thesis_id=request.thesis_id,
            query=request.query,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
