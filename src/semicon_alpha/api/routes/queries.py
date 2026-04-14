from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import CreateSavedQueryRequest, RunSavedQueryResponse


router = APIRouter(prefix="/queries", tags=["queries"])


@router.get("")
def list_queries(services: APIServices = Depends(get_services)) -> list[dict]:
    return services.queries.list_queries()


@router.post("")
def create_query(
    request: CreateSavedQueryRequest,
    services: APIServices = Depends(get_services),
) -> dict:
    return services.queries.create_query(
        name=request.name,
        query_text=request.query_text,
        query_type=request.query_type,
        filters=request.filters,
    )


@router.get("/{query_id}/run", response_model=RunSavedQueryResponse)
def run_query(
    query_id: str,
    services: APIServices = Depends(get_services),
) -> RunSavedQueryResponse:
    try:
        return RunSavedQueryResponse(**services.queries.run_query(query_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
