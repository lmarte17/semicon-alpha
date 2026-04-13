from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import EntityWorkspace


router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/{entity_id}", response_model=EntityWorkspace)
def get_entity_workspace(
    entity_id: str,
    services: APIServices = Depends(get_services),
) -> EntityWorkspace:
    try:
        return EntityWorkspace(**services.entities.get_entity_workspace(entity_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{entity_id}/neighbors")
def get_entity_neighbors(
    entity_id: str,
    relationship_type: list[str] | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    services: APIServices = Depends(get_services),
) -> dict:
    try:
        return services.graph.get_neighbors(
            entity_id,
            relationship_types=relationship_type,
            min_confidence=min_confidence,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{entity_id}/events")
def get_entity_events(
    entity_id: str,
    limit: int = Query(default=10, ge=1, le=100),
    services: APIServices = Depends(get_services),
) -> list[dict]:
    return services.entities.get_entity_events(entity_id, limit=limit)


@router.get("/{entity_id}/effects")
def get_entity_effects(
    entity_id: str,
    services: APIServices = Depends(get_services),
) -> list[dict]:
    try:
        workspace = services.entities.get_entity_workspace(entity_id)
        return workspace["effect_pathways"]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
