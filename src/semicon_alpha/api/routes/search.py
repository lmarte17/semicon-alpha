from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import SearchResponse


router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=8, ge=1, le=25),
    services: APIServices = Depends(get_services),
) -> SearchResponse:
    return SearchResponse(**services.search.search(q, limit=limit))
