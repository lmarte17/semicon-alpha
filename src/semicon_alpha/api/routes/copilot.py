from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import CopilotQueryRequest, CopilotResponse


router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.post("/query", response_model=CopilotResponse)
def query_copilot(
    request: CopilotQueryRequest,
    services: APIServices = Depends(get_services),
) -> CopilotResponse:
    try:
        payload = services.copilot.query(
            query=request.query,
            event_id=request.event_id,
            entity_id=request.entity_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CopilotResponse(**payload)
