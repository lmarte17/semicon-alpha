from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

import pandas as pd

from semicon_alpha.llm.workflows import GeminiEmbeddingService, RetrievalEmbeddingInput
from semicon_alpha.models.records import RetrievalIndexRecord
from semicon_alpha.services.repository import WorldModelRepository
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, upsert_parquet


TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_\-\.]{1,}")
VECTOR_SIZE = 48
RETRIEVAL_INDEX_EMBEDDING_VERSION = "1"


class RetrievalIndexService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.repo = WorldModelRepository(settings)
        self.index_path = settings.processed_dir / "retrieval_index.parquet"
        self.embedding_service = GeminiEmbeddingService(settings)

    def run(self) -> dict[str, int]:
        updated_at = now_utc()
        source_records = (
            self._entity_records(updated_at)
            + self._event_records(updated_at)
            + self._document_records(updated_at)
            + self._theme_records(updated_at)
        )

        embedding_rows = pd.DataFrame()
        if self.settings.llm_runtime_enabled:
            try:
                embedding_rows = self.embedding_service.run(
                    self._embedding_inputs(source_records),
                    force=False,
                )
            except Exception:
                embedding_rows = pd.DataFrame()

        embedding_lookup = _embedding_lookup(embedding_rows)
        records = [
            self._record(
                item=item,
                updated_at=updated_at,
                embedding_info=embedding_lookup.get((item["item_id"], item["search_category"])),
            )
            for item in source_records
        ]
        frame = upsert_parquet(
            self.index_path,
            records,
            unique_keys=["item_id", "search_category"],
            sort_by=["search_category", "item_type", "title"],
        )
        self.catalog.refresh_processed_views()
        return {
            "record_count": len(frame),
            "embedding_count": 0 if embedding_rows.empty else len(embedding_rows),
        }

    def _entity_records(self, updated_at) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        graph_nodes = _safe_frame(lambda: self.repo.graph_nodes)
        for row in graph_nodes.to_dict(orient="records"):
            payload = _clean_record(row)
            metadata = _parse_json_value(payload.get("metadata_json"), {})
            aliases = _parse_json_list(metadata.get("aliases"))
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
                {
                    "item_id": payload["node_id"],
                    "item_type": payload["node_type"],
                    "search_category": "entities",
                    "title": payload["label"],
                    "subtitle": payload.get("node_type"),
                    "url": None,
                    "semantic_text": semantic_text,
                    "aliases": aliases,
                    "metadata": metadata,
                    "updated_at": updated_at,
                }
            )
        return records

    def _event_records(self, updated_at) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        events = _safe_frame(lambda: self.repo.events)
        for row in events.to_dict(orient="records"):
            payload = _clean_record(row)
            semantic_text = " ".join(
                filter(
                    None,
                    [
                        payload.get("headline"),
                        payload.get("summary"),
                        payload.get("event_type"),
                        payload.get("reasoning"),
                        " ".join(_parse_json_value(payload.get("primary_themes"), [])),
                        payload.get("primary_segment"),
                        " ".join(_parse_json_value(payload.get("uncertainty_flags"), [])),
                    ],
                )
            )
            records.append(
                {
                    "item_id": payload["event_id"],
                    "item_type": "event",
                    "search_category": "events",
                    "title": payload.get("headline") or payload["event_id"],
                    "subtitle": payload.get("event_type"),
                    "url": payload.get("canonical_url") or payload.get("source_url"),
                    "semantic_text": semantic_text,
                    "aliases": [],
                    "metadata": {
                        "direction": payload.get("direction"),
                        "severity": payload.get("severity"),
                    },
                    "updated_at": updated_at,
                }
            )
        return records

    def _document_records(self, updated_at) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        articles_enriched = _safe_frame(lambda: self.repo.articles_enriched)
        for row in articles_enriched.to_dict(orient="records"):
            payload = _clean_record(row)
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
                {
                    "item_id": payload["article_id"],
                    "item_type": "document",
                    "search_category": "documents",
                    "title": payload.get("title") or payload.get("canonical_url") or payload.get("source_url") or payload["article_id"],
                    "subtitle": payload.get("site_name"),
                    "url": payload.get("canonical_url") or payload.get("source_url"),
                    "semantic_text": semantic_text,
                    "aliases": [],
                    "metadata": {"fetch_status": payload.get("fetch_status")},
                    "updated_at": updated_at,
                }
            )
        return records

    def _theme_records(self, updated_at) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        theme_nodes = _safe_frame(lambda: self.repo.theme_nodes)
        for row in theme_nodes.to_dict(orient="records"):
            payload = _clean_record(row)
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
                {
                    "item_id": payload["node_id"],
                    "item_type": "theme",
                    "search_category": "themes",
                    "title": payload.get("theme_name") or payload["node_id"],
                    "subtitle": payload.get("node_category"),
                    "url": None,
                    "semantic_text": semantic_text,
                    "aliases": [],
                    "metadata": {"node_category": payload.get("node_category")},
                    "updated_at": updated_at,
                }
            )
        return records

    def _embedding_inputs(self, source_records: list[dict[str, Any]]) -> list[RetrievalEmbeddingInput]:
        rows: list[RetrievalEmbeddingInput] = []
        for item in source_records:
            chunks = _chunk_text(
                text=str(item["semantic_text"] or ""),
                max_chars=self.settings.llm_retrieval_chunk_chars,
                overlap_chars=self.settings.llm_retrieval_chunk_overlap_chars,
            )
            if item["item_type"] != "document":
                chunks = chunks[:1]
            for index, chunk_text in enumerate(chunks, start=1):
                chunk_id = (
                    f"{item['item_id']}::chunk:{index}"
                    if len(chunks) > 1
                    else str(item["item_id"])
                )
                rows.append(
                    RetrievalEmbeddingInput(
                        item_id=str(item["item_id"]),
                        item_type=str(item["item_type"]),
                        search_category=str(item["search_category"]),
                        chunk_id=chunk_id,
                        chunk_rank=index,
                        semantic_text=chunk_text,
                    )
                )
        return rows

    def _record(
        self,
        *,
        item: dict[str, Any],
        updated_at,
        embedding_info: dict[str, Any] | None,
    ) -> RetrievalIndexRecord:
        aliases = item.get("aliases") or []
        lexical_terms = tokenize_for_retrieval(" ".join([str(item["semantic_text"]), *aliases]))
        if embedding_info is None:
            embedding = embed_terms(lexical_terms)
            embedding_model = None
            embedding_version = None
            chunk_count = 1
        else:
            embedding = embedding_info["embedding_vector"]
            embedding_model = embedding_info["embedding_model"]
            embedding_version = embedding_info["embedding_version"]
            chunk_count = int(embedding_info["chunk_count"])
        return RetrievalIndexRecord(
            item_id=str(item["item_id"]),
            item_type=str(item["item_type"]),
            search_category=str(item["search_category"]),
            title=str(item["title"]),
            subtitle=item.get("subtitle"),
            url=item.get("url"),
            semantic_text=str(item["semantic_text"]),
            aliases=aliases,
            lexical_terms=lexical_terms,
            embedding_vector=embedding,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            chunk_count=chunk_count,
            metadata_json=item.get("metadata"),
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
        return []
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except Exception:  # pragma: no cover - defensive
                parsed = None
            if isinstance(parsed, list):
                return [float(item) for item in parsed]
    return []


def _metadata_text(metadata: dict[str, Any] | list[Any] | None) -> str:
    if isinstance(metadata, dict):
        values: list[str] = []
        for value in metadata.values():
            if isinstance(value, list):
                values.extend(str(item) for item in value)
            elif value is not None:
                values.append(str(value))
        return " ".join(values)
    if isinstance(metadata, list):
        return " ".join(str(item) for item in metadata)
    return ""


def _safe_frame(loader) -> pd.DataFrame:
    try:
        return loader()
    except FileNotFoundError:
        return pd.DataFrame()


def _embedding_lookup(frame: pd.DataFrame) -> dict[tuple[str, str], dict[str, Any]]:
    if frame.empty:
        return {}
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for (item_id, search_category), group in frame.groupby(["item_id", "search_category"], dropna=False):
        vectors = [parse_embedding(value) for value in group["embedding_vector"].tolist()]
        vectors = [vector for vector in vectors if vector]
        if not vectors:
            continue
        averaged = _average_vectors(vectors)
        first_row = group.iloc[0]
        lookup[(str(item_id), str(search_category))] = {
            "embedding_vector": averaged,
            "embedding_model": first_row.get("embedding_model"),
            "embedding_version": first_row.get("embedding_version") or RETRIEVAL_INDEX_EMBEDDING_VERSION,
            "chunk_count": len(group),
        }
    return lookup


def _average_vectors(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    width = len(vectors[0])
    sums = [0.0] * width
    for vector in vectors:
        if len(vector) != width:
            continue
        for index, value in enumerate(vector):
            sums[index] += value
    averaged = [value / len(vectors) for value in sums]
    norm = math.sqrt(sum(value * value for value in averaged))
    if norm <= 0:
        return averaged
    return [round(value / norm, 6) for value in averaged]


def _chunk_text(*, text: str, max_chars: int, overlap_chars: int) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return [""]
    if len(normalized) <= max_chars:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start + 200:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(0, end - overlap_chars)
    return chunks or [normalized]


def _parse_json_value(value: Any, default: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, (list, dict)):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _parse_json_list(value: Any) -> list[str]:
    parsed = _parse_json_value(value, None)
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    if parsed is None:
        text = str(value).strip() if value is not None else ""
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]
    return [str(parsed)]


def _clean_record(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, float) and pd.isna(value):
            cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned
