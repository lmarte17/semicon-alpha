from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import AddWatchlistItemRequest, CreateWatchlistRequest, WatchlistWorkspace


router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("")
def list_watchlists(services: APIServices = Depends(get_services)) -> list[dict]:
    return services.watchlists.list_watchlists()


@router.post("", response_model=WatchlistWorkspace)
def create_watchlist(
    request: CreateWatchlistRequest,
    services: APIServices = Depends(get_services),
) -> WatchlistWorkspace:
    watchlist = services.watchlists.create_watchlist(request.name, request.description)
    payload = services.watchlists.get_watchlist(watchlist["watchlist_id"], alerts=services.alerts.list_alerts(refresh=True))
    return WatchlistWorkspace(**payload)


@router.get("/{watchlist_id}", response_model=WatchlistWorkspace)
def get_watchlist(
    watchlist_id: str,
    services: APIServices = Depends(get_services),
) -> WatchlistWorkspace:
    try:
        payload = services.watchlists.get_watchlist(watchlist_id, alerts=services.alerts.list_alerts(refresh=True))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return WatchlistWorkspace(**payload)


@router.post("/{watchlist_id}/items")
def add_watchlist_item(
    watchlist_id: str,
    request: AddWatchlistItemRequest,
    services: APIServices = Depends(get_services),
) -> dict:
    try:
        return services.watchlists.add_item(
            watchlist_id=watchlist_id,
            item_type=request.item_type,
            item_id=request.item_id,
            label=request.label,
            metadata=request.metadata,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/items/{item_id}")
def delete_watchlist_item(
    item_id: str,
    services: APIServices = Depends(get_services),
) -> dict:
    services.watchlists.remove_item(item_id)
    return {"ok": True, "item_id": item_id}
