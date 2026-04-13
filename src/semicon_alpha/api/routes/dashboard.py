from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import DashboardOverview


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
def get_dashboard_overview(
    limit: int = Query(default=12, ge=1, le=50),
    services: APIServices = Depends(get_services),
) -> DashboardOverview:
    return DashboardOverview(**services.dashboard.get_overview(limit=limit))
