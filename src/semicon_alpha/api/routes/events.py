from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import EventWorkspace


router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
def list_events(
    limit: int = Query(default=50, ge=1, le=100),
    query: str | None = Query(default=None),
    services: APIServices = Depends(get_services),
) -> list[dict]:
    return services.events.list_events(limit=limit, query=query)


@router.get("/{event_id}", response_model=EventWorkspace)
def get_event_workspace(
    event_id: str,
    services: APIServices = Depends(get_services),
) -> EventWorkspace:
    try:
        return EventWorkspace(**services.events.get_event_workspace(event_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{event_id}/impacts")
def get_event_impacts(
    event_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    services: APIServices = Depends(get_services),
) -> list[dict]:
    return services.events.get_event_impacts(event_id, limit=limit)


@router.get("/{event_id}/evidence")
def get_event_evidence(
    event_id: str,
    services: APIServices = Depends(get_services),
) -> dict:
    try:
        return services.evidence.get_event_evidence(event_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
