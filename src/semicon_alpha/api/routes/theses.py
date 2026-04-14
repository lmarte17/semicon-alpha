from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import CreateThesisRequest, ThesisUpdateRequest, ThesisWorkspace


router = APIRouter(prefix="/theses", tags=["theses"])


@router.get("")
def list_theses(services: APIServices = Depends(get_services)) -> list[dict]:
    return services.theses.list_theses()


@router.post("", response_model=ThesisWorkspace)
def create_thesis(
    request: CreateThesisRequest,
    services: APIServices = Depends(get_services),
) -> ThesisWorkspace:
    payload = services.theses.create_thesis(
        title=request.title,
        statement=request.statement,
        stance=request.stance,
        confidence=request.confidence,
        status=request.status,
        time_horizon=request.time_horizon,
        links=None
        if request.links is None
        else [
            {
                "item_type": row.item_type,
                "item_id": row.item_id,
                "relationship": row.relationship,
                "label": row.label,
                "metadata": row.metadata,
            }
            for row in request.links
        ],
        initial_update=request.initial_update,
    )
    return ThesisWorkspace(**payload)


@router.get("/{thesis_id}", response_model=ThesisWorkspace)
def get_thesis(
    thesis_id: str,
    services: APIServices = Depends(get_services),
) -> ThesisWorkspace:
    try:
        payload = services.theses.get_thesis_workspace(
            thesis_id,
            alerts=services.alerts.list_alerts(refresh=True),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ThesisWorkspace(**payload)


@router.post("/{thesis_id}/updates")
def add_thesis_update(
    thesis_id: str,
    request: ThesisUpdateRequest,
    services: APIServices = Depends(get_services),
) -> dict:
    try:
        return services.theses.add_update(
            thesis_id=thesis_id,
            summary=request.summary,
            confidence=request.confidence,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
