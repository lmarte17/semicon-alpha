from __future__ import annotations

from typing import Any

from semicon_alpha.appstate import AppStateRepository
from semicon_alpha.services.search import SearchService


class SavedQueryService:
    def __init__(self, appstate: AppStateRepository, search_service: SearchService) -> None:
        self.appstate = appstate
        self.search_service = search_service

    def list_queries(self) -> list[dict[str, Any]]:
        return self.appstate.list_saved_queries()

    def create_query(
        self,
        name: str,
        query_text: str,
        query_type: str = "global_search",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.appstate.create_saved_query(
            name=name,
            query_text=query_text,
            query_type=query_type,
            filters=filters,
        )

    def run_query(self, query_id: str) -> dict[str, Any]:
        query = self.appstate.get_saved_query(query_id)
        if query is None:
            raise KeyError(f"Unknown query_id: {query_id}")
        query_type = query.get("query_type", "global_search")
        if query_type != "global_search":
            raise KeyError(f"Unsupported saved query type: {query_type}")
        results = self.search_service.search(query["query_text"], limit=8)
        return {"saved_query": query, "results": results}
