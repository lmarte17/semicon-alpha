from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import AddBoardItemRequest, BoardWorkspace, CreateBoardRequest


router = APIRouter(prefix="/boards", tags=["boards"])


@router.get("")
def list_boards(services: APIServices = Depends(get_services)) -> list[dict]:
    return services.boards.list_boards()


@router.post("", response_model=BoardWorkspace)
def create_board(
    request: CreateBoardRequest,
    services: APIServices = Depends(get_services),
) -> BoardWorkspace:
    board = services.boards.create_board(request.name, request.description, request.layout)
    payload = services.boards.get_board(board["board_id"], alerts=services.alerts.list_alerts(refresh=True))
    return BoardWorkspace(**payload)


@router.get("/{board_id}", response_model=BoardWorkspace)
def get_board(
    board_id: str,
    services: APIServices = Depends(get_services),
) -> BoardWorkspace:
    try:
        payload = services.boards.get_board(board_id, alerts=services.alerts.list_alerts(refresh=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BoardWorkspace(**payload)


@router.post("/{board_id}/items")
def add_board_item(
    board_id: str,
    request: AddBoardItemRequest,
    services: APIServices = Depends(get_services),
) -> dict:
    try:
        return services.boards.add_item(
            board_id=board_id,
            item_type=request.item_type,
            item_id=request.item_id,
            title=request.title,
            content=request.content,
            position=request.position,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
