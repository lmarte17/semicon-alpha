from __future__ import annotations

from typing import Any

from semicon_alpha.services.helpers import clean_record
from semicon_alpha.services.repository import WorldModelRepository


class SearchService:
    def __init__(self, repo: WorldModelRepository) -> None:
        self.repo = repo

    def search(self, query: str, limit: int = 8) -> dict[str, list[dict[str, Any]]]:
        needle = query.lower().strip()
        if not needle:
            return {"entities": [], "events": [], "documents": [], "themes": []}

        return {
            "entities": self._search_entities(needle, limit),
            "events": self._search_events(needle, limit),
            "documents": self._search_documents(needle, limit),
            "themes": self._search_themes(needle, limit),
        }

    def _search_entities(self, needle: str, limit: int) -> list[dict[str, Any]]:
        nodes = self.repo.graph_nodes.copy()
        if nodes.empty:
            return []
        label_match = nodes["label"].fillna("").str.lower().str.contains(needle)
        type_match = nodes["node_type"].fillna("").str.lower().str.contains(needle)
        ticker_match = nodes["ticker"].fillna("").str.lower().str.contains(needle) if "ticker" in nodes.columns else False
        frame = nodes[label_match | type_match | ticker_match].head(limit)
        return [
            {
                "id": row["node_id"],
                "type": "entity",
                "title": row["label"],
                "subtitle": row.get("node_type"),
            }
            for row in frame.to_dict(orient="records")
        ]

    def _search_events(self, needle: str, limit: int) -> list[dict[str, Any]]:
        events = self.repo.events
        if events.empty:
            return []
        mask = (
            events["headline"].fillna("").str.lower().str.contains(needle)
            | events["event_type"].fillna("").str.lower().str.contains(needle)
            | events["summary"].fillna("").str.lower().str.contains(needle)
        )
        frame = events[mask].head(limit)
        return [
            {
                "id": row["event_id"],
                "type": "event",
                "title": row["headline"],
                "subtitle": row.get("event_type"),
            }
            for row in frame.to_dict(orient="records")
        ]

    def _search_documents(self, needle: str, limit: int) -> list[dict[str, Any]]:
        docs = self.repo.articles_enriched
        if docs.empty:
            return []
        mask = (
            docs["title"].fillna("").str.lower().str.contains(needle)
            | docs["description"].fillna("").str.lower().str.contains(needle)
            | docs["excerpt"].fillna("").str.lower().str.contains(needle)
            | docs["body_text"].fillna("").str.lower().str.contains(needle)
        )
        frame = docs[mask].head(limit)
        return [
            {
                "id": row["article_id"],
                "type": "document",
                "title": row.get("title") or row.get("canonical_url") or row.get("source_url"),
                "subtitle": row.get("site_name"),
                "url": row.get("canonical_url") or row.get("source_url"),
            }
            for row in frame.to_dict(orient="records")
        ]

    def _search_themes(self, needle: str, limit: int) -> list[dict[str, Any]]:
        themes = self.repo.theme_nodes
        if themes.empty:
            return []
        mask = (
            themes["theme_name"].fillna("").str.lower().str.contains(needle)
            | themes["description"].fillna("").str.lower().str.contains(needle)
            | themes["node_category"].fillna("").str.lower().str.contains(needle)
        )
        frame = themes[mask].head(limit)
        return [
            {
                "id": row["node_id"],
                "type": "theme",
                "title": row["theme_name"],
                "subtitle": row.get("node_category"),
            }
            for row in frame.to_dict(orient="records")
        ]
