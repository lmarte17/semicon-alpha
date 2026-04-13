from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import PathTraceRequest, PathTraceResponse


router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/path-trace", response_model=PathTraceResponse)
def path_trace(
    request: PathTraceRequest,
    services: APIServices = Depends(get_services),
) -> PathTraceResponse:
    try:
        payload = services.graph.trace_path(
            source_id=request.source_id,
            target_id=request.target_id,
            max_hops=request.max_hops,
            relationship_types=request.relationship_types,
            min_confidence=request.min_confidence,
            max_paths=request.max_paths,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PathTraceResponse(**payload)
