from __future__ import annotations

import json
from typing import Any

from semicon_alpha.retrieval.index import (
    cosine_similarity,
    embed_terms,
    parse_embedding,
    tokenize_for_retrieval,
)
from semicon_alpha.llm.workflows import GeminiEmbeddingService
from semicon_alpha.services.repository import WorldModelRepository
from semicon_alpha.settings import Settings


class SearchService:
    def __init__(self, repo: WorldModelRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings
        self.embedding_service = GeminiEmbeddingService(settings)

    def search(self, query: str, limit: int = 8) -> dict[str, list[dict[str, Any]]]:
        needle = query.lower().strip()
        if not needle:
            return {"entities": [], "events": [], "documents": [], "themes": []}

        if not self.repo.retrieval_index.empty:
            return {
                "entities": self._search_index_category(query, "entities", limit),
                "events": self._search_index_category(query, "events", limit),
                "documents": self._search_index_category(query, "documents", limit),
                "themes": self._search_index_category(query, "themes", limit),
            }

        return {
            "entities": self._search_entities(needle, limit),
            "events": self._search_events(needle, limit),
            "documents": self._search_documents(needle, limit),
            "themes": self._search_themes(needle, limit),
        }

    def _search_index_category(
        self,
        query: str,
        category: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        query_terms = tokenize_for_retrieval(query)
        if not query_terms:
            return []
        frame = self.repo.retrieval_index
        frame = frame.loc[frame["search_category"] == category]
        if frame.empty:
            return []
        query_vector = self._query_embedding(query, query_terms, frame)

        scored = []
        needle = query.lower().strip()
        for row in frame.to_dict(orient="records"):
            title = str(row.get("title") or "")
            subtitle = row.get("subtitle")
            semantic_text = str(row.get("semantic_text") or "")
            aliases = _parse_list(row.get("aliases"))
            lexical_terms = set(_parse_list(row.get("lexical_terms")))
            matched_terms = lexical_terms.intersection(query_terms)
            lexical_score = len(matched_terms) / max(len(query_terms), 1)
            if needle in title.lower():
                lexical_score += 0.8
            elif needle in semantic_text.lower():
                lexical_score += 0.45
            elif aliases and any(needle in alias.lower() for alias in aliases):
                lexical_score += 0.55
            vector_score = cosine_similarity(query_vector, parse_embedding(row.get("embedding_vector")))
            score = (0.58 * vector_score) + (0.42 * min(lexical_score, 1.5))
            if score <= 0.08:
                continue
            scored.append(
                {
                    "id": row["item_id"],
                    "type": _result_type_for_category(category),
                    "title": title,
                    "subtitle": subtitle,
                    "url": row.get("url"),
                    "score": round(score, 4),
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    def _query_embedding(
        self,
        query: str,
        query_terms: list[str],
        frame,
    ) -> list[float]:
        has_model_embeddings = "embedding_model" in frame.columns and frame["embedding_model"].notna().any()
        if has_model_embeddings and self.settings.llm_runtime_enabled:
            try:
                vector = self.embedding_service.embed_query(query)
                if vector:
                    return vector
            except Exception:
                pass
        return embed_terms(query_terms)

    def _search_entities(self, needle: str, limit: int) -> list[dict[str, Any]]:
        nodes = self.repo.graph_nodes.copy()
        if nodes.empty:
            return []
        label_match = nodes["label"].fillna("").str.lower().str.contains(needle)
        type_match = nodes["node_type"].fillna("").str.lower().str.contains(needle)
        ticker_match = nodes["ticker"].fillna("").str.lower().str.contains(needle) if "ticker" in nodes.columns else False
        description_match = (
            nodes["description"].fillna("").str.lower().str.contains(needle)
            if "description" in nodes.columns
            else False
        )
        frame = nodes[label_match | type_match | ticker_match | description_match].head(limit)
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


def _parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except Exception:  # pragma: no cover - defensive
                parsed = []
            return [str(item) for item in parsed] if isinstance(parsed, list) else []
        return [stripped]
    return [str(value)]


def _result_type_for_category(category: str) -> str:
    if category == "entities":
        return "entity"
    if category == "events":
        return "event"
    if category == "documents":
        return "document"
    return "theme"
