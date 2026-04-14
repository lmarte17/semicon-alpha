from __future__ import annotations

from typing import Any

from semicon_alpha.appstate import AppStateRepository
from semicon_alpha.services.operational_support import (
    event_summary_card,
    matched_event_rows,
    related_alerts_for_items,
    resolve_item_label,
)
from semicon_alpha.services.repository import WorldModelRepository


class WatchlistService:
    def __init__(self, repo: WorldModelRepository, appstate: AppStateRepository) -> None:
        self.repo = repo
        self.appstate = appstate

    def list_watchlists(self) -> list[dict[str, Any]]:
        return self.appstate.list_watchlists()

    def create_watchlist(self, name: str, description: str | None = None) -> dict[str, Any]:
        return self.appstate.create_watchlist(name=name, description=description)

    def add_item(
        self,
        watchlist_id: str,
        item_type: str,
        item_id: str,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item_label = label or resolve_item_label(self.repo, item_type, item_id)
        return self.appstate.add_watchlist_item(
            watchlist_id=watchlist_id,
            item_type=item_type,
            item_id_value=item_id,
            label=item_label,
            metadata=metadata,
        )

    def remove_item(self, item_id: str) -> None:
        self.appstate.delete_watchlist_item(item_id)

    def get_watchlist(self, watchlist_id: str, alerts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        watchlist = self.appstate.get_watchlist(watchlist_id)
        if watchlist is None:
            raise KeyError(f"Unknown watchlist_id: {watchlist_id}")
        items = self.appstate.list_watchlist_items(watchlist_id)

        feed_rows: list[dict[str, Any]] = []
        item_ids: list[str] = []
        for item in items:
            item_ids.append(str(item["item_id_value"]))
            matches = matched_event_rows(self.repo, item["item_type"], item["item_id_value"], limit=8)
            for event_row in matches:
                feed_rows.append(event_summary_card(self.repo, event_row))

        deduped_feed = list({row["event_id"]: row for row in feed_rows}.values())
        deduped_feed.sort(key=lambda row: row.get("published_at_utc") or "", reverse=True)

        current_alerts = alerts or []
        related_alerts = related_alerts_for_items(current_alerts, item_ids)
        return {
            "watchlist": watchlist,
            "items": items,
            "event_feed": deduped_feed[:20],
            "alerts": related_alerts[:20],
        }
