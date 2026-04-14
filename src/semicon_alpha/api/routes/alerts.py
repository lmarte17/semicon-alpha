from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import AlertListResponse


router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
def list_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    status: str = Query(default="active"),
    refresh: bool = Query(default=True),
    services: APIServices = Depends(get_services),
) -> AlertListResponse:
    return AlertListResponse(alerts=services.alerts.list_alerts(limit=limit, status=status, refresh=refresh))


@router.post("/refresh")
def refresh_alerts(services: APIServices = Depends(get_services)) -> dict:
    return services.alerts.refresh_alerts()


@router.post("/{alert_id}/dismiss")
def dismiss_alert(
    alert_id: str,
    services: APIServices = Depends(get_services),
) -> dict:
    payload = services.alerts.dismiss_alert(alert_id)
    return {"alert": payload}
