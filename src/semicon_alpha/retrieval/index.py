from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

import pandas as pd

from semicon_alpha.models.records import RetrievalIndexRecord
from semicon_alpha.services.helpers import clean_record, parse_json_list, parse_json_value
from semicon_alpha.services.repository import WorldModelRepository
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, upsert_parquet


TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_\-\.]{1,}")
VECTOR_SIZE = 48


class RetrievalIndexService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.repo = WorldModelRepository(settings)
        self.index_path = settings.processed_dir / "retrieval_index.parquet"

    def run(self) -> dict[str, int]:
        updated_at = now_utc()
        records = (
            self._entity_records(updated_at)
            + self._event_records(updated_at)
            + self._document_records(updated_at)
            + self._theme_records(updated_at)
        )
        frame = upsert_parquet(
            self.index_path,
            records,
            unique_keys=["item_id", "search_category"],
            sort_by=["search_category", "item_type", "title"],
        )
        self.catalog.refresh_processed_views()
        return {"record_count": len(frame)}

    def _entity_records(self, updated_at) -> list[RetrievalIndexRecord]:
        records: list[RetrievalIndexRecord] = []
        graph_nodes = _safe_frame(lambda: self.repo.graph_nodes)
        for row in graph_nodes.to_dict(orient="records"):
            payload = clean_record(row)
            metadata = parse_json_value(payload.get("metadata_json"), {})
            aliases = parse_json_list(metadata.get("aliases"))
            semantic_text = " ".join(
                filter(
                    None,
                    [
                        payload.get("label"),
                        payload.get("description"),
                        payload.get("ticker"),
                        payload.get("node_type"),
                        _metadata_text(metadata),
                        " ".join(aliases),
                    ],
                )
            )
            records.append(
                self._record(
                    item_id=payload["node_id"],
                    item_type=payload["node_type"],
                    search_category="entities",
                    title=payload["label"],
                    subtitle=payload.get("node_type"),
                    semantic_text=semantic_text,
                    aliases=aliases,
                    metadata=metadata,
                    updated_at=updated_at,
                )
            )
        return records

    def _event_records(self, updated_at) -> list[RetrievalIndexRecord]:
        records: list[RetrievalIndexRecord] = []
        events = _safe_frame(lambda: self.repo.events)
        for row in events.to_dict(orient="records"):
            payload = clean_record(row)
            semantic_text = " ".join(
                filter(
                    None,
                    [
                        payload.get("headline"),
                        payload.get("summary"),
                        payload.get("event_type"),
                        payload.get("reasoning"),
                        " ".join(parse_json_value(payload.get("primary_themes"), [])),
                        payload.get("primary_segment"),
                    ],
                )
            )
            records.append(
                self._record(
                    item_id=payload["event_id"],
                    item_type="event",
                    search_category="events",
                    title=payload.get("headline") or payload["event_id"],
                    subtitle=payload.get("event_type"),
                    url=payload.get("canonical_url") or payload.get("source_url"),
                    semantic_text=semantic_text,
                    aliases=[],
                    metadata={
                        "direction": payload.get("direction"),
                        "severity": payload.get("severity"),
                    },
                    updated_at=updated_at,
                )
            )
        return records

    def _document_records(self, updated_at) -> list[RetrievalIndexRecord]:
        records: list[RetrievalIndexRecord] = []
        articles_enriched = _safe_frame(lambda: self.repo.articles_enriched)
        for row in articles_enriched.to_dict(orient="records"):
            payload = clean_record(row)
            semantic_text = " ".join(
                filter(
                    None,
                    [
                        payload.get("title"),
                        payload.get("description"),
                        payload.get("excerpt"),
                        payload.get("body_text"),
                        payload.get("site_name"),
                    ],
                )
            )
            records.append(
                self._record(
                    item_id=payload["article_id"],
                    item_type="document",
                    search_category="documents",
                    title=payload.get("title") or payload.get("canonical_url") or payload.get("source_url") or payload["article_id"],
                    subtitle=payload.get("site_name"),
                    url=payload.get("canonical_url") or payload.get("source_url"),
                    semantic_text=semantic_text,
                    aliases=[],
                    metadata={"fetch_status": payload.get("fetch_status")},
                    updated_at=updated_at,
                )
            )
        return records

    def _theme_records(self, updated_at) -> list[RetrievalIndexRecord]:
        records: list[RetrievalIndexRecord] = []
        theme_nodes = _safe_frame(lambda: self.repo.theme_nodes)
        for row in theme_nodes.to_dict(orient="records"):
            payload = clean_record(row)
            semantic_text = " ".join(
                filter(
                    None,
                    [
                        payload.get("theme_name"),
                        payload.get("description"),
                        payload.get("node_category"),
                    ],
                )
            )
            records.append(
                self._record(
                    item_id=payload["node_id"],
                    item_type="theme",
                    search_category="themes",
                    title=payload.get("theme_name") or payload["node_id"],
                    subtitle=payload.get("node_category"),
                    semantic_text=semantic_text,
                    aliases=[],
                    metadata={"node_category": payload.get("node_category")},
                    updated_at=updated_at,
                )
            )
        return records

    def _record(
        self,
        *,
        item_id: str,
        item_type: str,
        search_category: str,
        title: str,
        semantic_text: str,
        updated_at,
        subtitle: str | None = None,
        url: str | None = None,
        aliases: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RetrievalIndexRecord:
        aliases = aliases or []
        lexical_terms = tokenize_for_retrieval(" ".join([semantic_text, *aliases]))
        embedding = embed_terms(lexical_terms)
        return RetrievalIndexRecord(
            item_id=item_id,
            item_type=item_type,
            search_category=search_category,
            title=title,
            subtitle=subtitle,
            url=url,
            semantic_text=semantic_text,
            aliases=aliases,
            lexical_terms=lexical_terms,
            embedding_vector=embedding,
            metadata_json=metadata,
            updated_at_utc=updated_at,
        )


def tokenize_for_retrieval(text: str | None) -> list[str]:
    if not text:
        return []
    tokens = TOKEN_PATTERN.findall(text.lower())
    return list(dict.fromkeys(tokens))


def embed_terms(terms: list[str], vector_size: int = VECTOR_SIZE) -> list[float]:
    if not terms:
        return [0.0] * vector_size
    vector = [0.0] * vector_size
    for term in terms:
        bucket = int(hashlib.sha256(term.encode("utf-8")).hexdigest()[:8], 16) % vector_size
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right, strict=True)))


def parse_embedding(value: Any) -> list[float]:
    if value is None:
        return [0.0] * VECTOR_SIZE
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return [0.0] * VECTOR_SIZE
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except Exception:  # pragma: no cover - defensive
                parsed = None
            if isinstance(parsed, list):
                return [float(item) for item in parsed]
    return [0.0] * VECTOR_SIZE


def _metadata_text(metadata: dict[str, Any] | list[Any] | None) -> str:
    if not metadata:
        return ""
    payload = parse_json_value(metadata, {})
    if isinstance(payload, list):
        return " ".join(str(item) for item in payload)
    return " ".join(str(value) for value in payload.values() if value is not None)


def _safe_frame(loader) -> pd.DataFrame:
    try:
        return loader()
    except FileNotFoundError:
        return pd.DataFrame()
