from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import CreateNoteRequest


router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("")
def list_notes(
    subject_type: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
    board_id: str | None = Query(default=None),
    services: APIServices = Depends(get_services),
) -> list[dict]:
    return services.notes.list_notes(subject_type=subject_type, subject_id=subject_id, board_id=board_id)


@router.post("")
def create_note(
    request: CreateNoteRequest,
    services: APIServices = Depends(get_services),
) -> dict:
    return services.notes.create_note(
        subject_type=request.subject_type,
        subject_id=request.subject_id,
        body=request.body,
        title=request.title,
        stance=request.stance,
        board_id=request.board_id,
    )
