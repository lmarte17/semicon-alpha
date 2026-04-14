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


class BoardService:
    def __init__(self, repo: WorldModelRepository, appstate: AppStateRepository) -> None:
        self.repo = repo
        self.appstate = appstate

    def list_boards(self) -> list[dict[str, Any]]:
        return self.appstate.list_boards()

    def create_board(
        self,
        name: str,
        description: str | None = None,
        layout: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.appstate.create_board(name=name, description=description, layout=layout)

    def add_item(
        self,
        board_id: str,
        item_type: str,
        item_id: str | None = None,
        title: str | None = None,
        content: str | None = None,
        position: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_title = title
        if resolved_title is None and item_id is not None:
            resolved_title = resolve_item_label(self.repo, item_type, item_id)
        return self.appstate.add_board_item(
            board_id=board_id,
            item_type=item_type,
            item_id_value=item_id,
            title=resolved_title,
            content=content,
            position=position,
        )

    def get_board(self, board_id: str, alerts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        board = self.appstate.get_board(board_id)
        if board is None:
            raise KeyError(f"Unknown board_id: {board_id}")

        items = self.appstate.list_board_items(board_id)
        notes = self.appstate.list_notes(board_id=board_id)
        reports = [
            self.appstate.get_report(item["item_id_value"])
            for item in items
            if item["item_type"] == "report" and item.get("item_id_value")
        ]
        reports = [report for report in reports if report is not None]

        event_feed_rows: list[dict[str, Any]] = []
        tracked_item_ids: list[str] = []
        for item in items:
            item_id = item.get("item_id_value")
            if not item_id or item["item_type"] == "report":
                continue
            tracked_item_ids.append(str(item_id))
            if item["item_type"] in {"entity", "theme", "event_type", "segment"}:
                for event_row in matched_event_rows(self.repo, item["item_type"], item_id, limit=8):
                    event_feed_rows.append(event_summary_card(self.repo, event_row))

        deduped_feed = list({row["event_id"]: row for row in event_feed_rows}.values())
        deduped_feed.sort(key=lambda row: row.get("published_at_utc") or "", reverse=True)
        related_alerts = related_alerts_for_items(alerts or [], tracked_item_ids)
        return {
            "board": board,
            "items": items,
            "notes": notes,
            "reports": reports,
            "event_feed": deduped_feed[:20],
            "alerts": related_alerts[:20],
        }
