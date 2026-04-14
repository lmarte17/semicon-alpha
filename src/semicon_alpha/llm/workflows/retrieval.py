from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from semicon_alpha.llm.client import GeminiClient
from semicon_alpha.llm.logging import LLMJobLogger
from semicon_alpha.models.records import RetrievalEmbeddingRecord
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, sha256_text, stable_id, upsert_parquet


RETRIEVAL_EMBEDDING_VERSION = "1"


@dataclass(frozen=True)
class RetrievalEmbeddingInput:
    item_id: str
    item_type: str
    search_category: str
    chunk_id: str
    chunk_rank: int
    semantic_text: str


class GeminiEmbeddingService:
    def __init__(
        self,
        settings: Settings,
        *,
        client: GeminiClient | None = None,
        job_logger: LLMJobLogger | None = None,
    ) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.client = client or GeminiClient(settings)
        self.job_logger = job_logger or LLMJobLogger(settings.processed_dir / "llm_job_runs.parquet")
        self.output_path = settings.processed_dir / "retrieval_embeddings.parquet"

    def run(
        self,
        inputs: Iterable[RetrievalEmbeddingInput],
        *,
        force: bool = False,
    ) -> pd.DataFrame:
        input_rows = list(inputs)
        if not input_rows:
            return self.lookup([])
        if not self.settings.llm_runtime_enabled:
            return self.lookup([row.chunk_id for row in input_rows])

        pending = input_rows
        if not force and self.output_path.exists():
            existing = pd.read_parquet(self.output_path, columns=["chunk_id", "text_sha256"])
            existing_by_chunk = {
                str(row["chunk_id"]): str(row["text_sha256"] or "")
                for row in existing.to_dict(orient="records")
            }
            pending = [
                row for row in input_rows if existing_by_chunk.get(row.chunk_id) != sha256_text(row.semantic_text)
            ]

        records = [self._embed_row(row) for row in pending]
        if records:
            upsert_parquet(
                self.output_path,
                records,
                unique_keys=["embedding_id"],
                sort_by=["updated_at_utc", "item_id", "chunk_rank"],
            )
            self.catalog.refresh_processed_views()
        return self.lookup([row.chunk_id for row in input_rows])

    def lookup(self, chunk_ids: list[str]) -> pd.DataFrame:
        if not self.output_path.exists():
            return pd.DataFrame()
        frame = pd.read_parquet(self.output_path)
        if not chunk_ids:
            return frame
        return frame.loc[frame["chunk_id"].isin(chunk_ids)].copy()

    def embed_query(self, query: str) -> list[float]:
        if not self.settings.llm_runtime_enabled:
            return []
        result = self.client.embed_text(
            text=query,
            model_name=self.settings.gemini_embedding_model,
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=self.settings.gemini_embedding_output_dimensionality,
        )
        return result.embedding_vector

    def _embed_row(self, row: RetrievalEmbeddingInput) -> RetrievalEmbeddingRecord:
        started_at = now_utc()
        request_payload = {
            "item_id": row.item_id,
            "chunk_id": row.chunk_id,
            "task_type": "RETRIEVAL_DOCUMENT",
            "text_sha256": sha256_text(row.semantic_text),
        }
        try:
            result = self.client.embed_text(
                text=row.semantic_text,
                model_name=self.settings.gemini_embedding_model,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.settings.gemini_embedding_output_dimensionality,
            )
            self.job_logger.log(
                workflow="retrieval_embedding",
                source_id=row.chunk_id,
                status="success",
                model_name=result.model_name,
                prompt_version="retrieval_embedding_v1",
                schema_name="embedding_vector",
                schema_version=RETRIEVAL_EMBEDDING_VERSION,
                request_payload=request_payload,
                started_at_utc=result.started_at_utc,
                completed_at_utc=result.completed_at_utc,
                usage_metadata=result.raw_response.get("usageMetadata"),
                response_preview=f"embedding_length={len(result.embedding_vector)}",
                metadata={"item_id": row.item_id, "search_category": row.search_category},
            )
            return RetrievalEmbeddingRecord(
                embedding_id=stable_id("retrembed", row.chunk_id, sha256_text(row.semantic_text)),
                item_id=row.item_id,
                item_type=row.item_type,
                search_category=row.search_category,
                chunk_id=row.chunk_id,
                chunk_rank=row.chunk_rank,
                embedding_model=result.model_name,
                embedding_version=RETRIEVAL_EMBEDDING_VERSION,
                semantic_text=row.semantic_text,
                text_sha256=sha256_text(row.semantic_text),
                embedding_vector=result.embedding_vector,
                updated_at_utc=now_utc(),
            )
        except Exception as exc:  # pragma: no cover - tested via fallback search behavior
            self.job_logger.log(
                workflow="retrieval_embedding",
                source_id=row.chunk_id,
                status="error",
                model_name=self.settings.gemini_embedding_model,
                prompt_version="retrieval_embedding_v1",
                schema_name="embedding_vector",
                schema_version=RETRIEVAL_EMBEDDING_VERSION,
                request_payload=request_payload,
                started_at_utc=started_at,
                completed_at_utc=now_utc(),
                error_message=str(exc),
                metadata={"item_id": row.item_id, "search_category": row.search_category},
            )
            raise
