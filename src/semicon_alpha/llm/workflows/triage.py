from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import pandas as pd

from semicon_alpha.llm.client import GeminiClient
from semicon_alpha.llm.config import LLMStructuredCallConfig, ModelTier
from semicon_alpha.llm.logging import LLMJobLogger
from semicon_alpha.llm.prompts import (
    ARTICLE_TRIAGE_PROMPT_VERSION,
    ARTICLE_TRIAGE_SYSTEM_PROMPT,
    render_article_triage_prompt,
)
from semicon_alpha.llm.schemas import ArticleTriageResponse
from semicon_alpha.models.records import ArticleLLMTriageRecord
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, sha256_text, upsert_parquet


ARTICLE_TRIAGE_SCHEMA_VERSION = "1"


class ArticleTriageService:
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
        self.output_path = settings.processed_dir / "article_llm_triage.parquet"
        self.job_log_path = settings.processed_dir / "llm_job_runs.parquet"
        self.job_logger = job_logger or LLMJobLogger(self.job_log_path)

    def run(
        self,
        frame: pd.DataFrame,
        *,
        force: bool = False,
    ) -> pd.DataFrame:
        if frame.empty:
            return self.lookup([])
        if not self.settings.llm_runtime_enabled:
            return self.lookup(frame["article_id"].astype(str).tolist())

        working = frame.copy()
        working["triage_content_sha256"] = working.apply(_triage_content_sha, axis=1)

        if not force and self.output_path.exists():
            existing = pd.read_parquet(
                self.output_path,
                columns=["article_id", "content_sha256"],
            )
            existing_by_article = {
                str(row["article_id"]): str(row["content_sha256"] or "")
                for row in existing.to_dict(orient="records")
            }
            mask = working.apply(
                lambda row: existing_by_article.get(str(row["article_id"])) != str(row["triage_content_sha256"]),
                axis=1,
            )
            working = working.loc[mask].copy()

        records: list[ArticleLLMTriageRecord] = []
        for row in working.to_dict(orient="records"):
            records.append(self._triage_article(row))

        if records:
            upsert_parquet(
                self.output_path,
                records,
                unique_keys=["article_id"],
                sort_by=["processed_at_utc"],
            )
            self.catalog.refresh_processed_views()
        return self.lookup(frame["article_id"].astype(str).tolist())

    def lookup(self, article_ids: list[str]) -> pd.DataFrame:
        if not self.output_path.exists():
            return pd.DataFrame()
        frame = pd.read_parquet(self.output_path)
        if not article_ids:
            return frame
        return frame.loc[frame["article_id"].isin(article_ids)].copy()

    def should_allow(self, triage_row: dict[str, Any] | None) -> bool:
        if not triage_row:
            return True
        if bool(triage_row.get("abstain")) or bool(triage_row.get("needs_review")):
            return True
        confidence = _coerce_float(triage_row.get("confidence"))
        if confidence < self.settings.llm_article_triage_min_confidence:
            return True
        return bool(triage_row.get("is_semiconductor_relevant")) and bool(
            triage_row.get("is_event_worthy")
        )

    def _triage_article(self, row: dict[str, Any]) -> ArticleLLMTriageRecord:
        prompt_payload = _prompt_payload(row)
        prompt = render_article_triage_prompt(prompt_payload)
        processed_at = now_utc()
        call_config = LLMStructuredCallConfig(
            workflow="article_triage",
            prompt_version=ARTICLE_TRIAGE_PROMPT_VERSION,
            schema_name="ArticleTriageResponse",
            schema_version=ARTICLE_TRIAGE_SCHEMA_VERSION,
            model_tier=ModelTier.FLASH,
            temperature=0.0,
            max_output_tokens=500,
        )
        request_payload = {
            "system_prompt": ARTICLE_TRIAGE_SYSTEM_PROMPT,
            "user_prompt": prompt,
            "article_id": str(row["article_id"]),
        }
        try:
            result = self.client.generate_structured(
                config=call_config,
                system_prompt=ARTICLE_TRIAGE_SYSTEM_PROMPT,
                user_prompt=prompt,
                response_model=ArticleTriageResponse,
            )
            parsed = ArticleTriageResponse.model_validate(result.parsed.model_dump())
            self.job_logger.log(
                workflow=call_config.workflow,
                source_id=str(row["article_id"]),
                status="success",
                model_name=result.model_name,
                prompt_version=call_config.prompt_version,
                schema_name=call_config.schema_name,
                schema_version=call_config.schema_version,
                request_payload=request_payload,
                started_at_utc=result.started_at_utc,
                completed_at_utc=result.completed_at_utc,
                usage_metadata=result.usage_metadata,
                response_preview=result.raw_text,
                metadata={"source_url": str(row.get("source_url") or "")},
            )
            return ArticleLLMTriageRecord(
                article_id=str(row["article_id"]),
                source_url=str(row["source_url"]),
                canonical_url=_coerce_optional_str(row.get("canonical_url")),
                source=_resolve_source(row),
                headline=_resolve_headline(row),
                content_sha256=_triage_content_sha(row),
                relevance_label=parsed.relevance_label,
                is_semiconductor_relevant=parsed.is_semiconductor_relevant,
                is_event_worthy=parsed.is_event_worthy,
                article_type=parsed.article_type,
                primary_subjects=parsed.primary_subjects[:6],
                mentioned_companies=parsed.mentioned_companies[:8],
                mentioned_technologies=parsed.mentioned_technologies[:8],
                mentioned_countries=parsed.mentioned_countries[:8],
                confidence=round(parsed.confidence, 4),
                abstain=parsed.abstain,
                needs_review=parsed.needs_review,
                rejection_reason=parsed.rejection_reason,
                reasoning_summary=parsed.reasoning_summary,
                model_name=result.model_name,
                prompt_version=call_config.prompt_version,
                schema_version=call_config.schema_version,
                processed_at_utc=processed_at,
            )
        except Exception as exc:  # pragma: no cover - exercised by fallback path tests
            self.job_logger.log(
                workflow=call_config.workflow,
                source_id=str(row["article_id"]),
                status="error",
                model_name=self.settings.gemini_flash_model,
                prompt_version=call_config.prompt_version,
                schema_name=call_config.schema_name,
                schema_version=call_config.schema_version,
                request_payload=request_payload,
                started_at_utc=processed_at,
                completed_at_utc=now_utc(),
                error_message=str(exc),
                metadata={"source_url": str(row.get("source_url") or "")},
            )
            return ArticleLLMTriageRecord(
                article_id=str(row["article_id"]),
                source_url=str(row["source_url"]),
                canonical_url=_coerce_optional_str(row.get("canonical_url")),
                source=_resolve_source(row),
                headline=_resolve_headline(row),
                content_sha256=_triage_content_sha(row),
                relevance_label="review_required",
                is_semiconductor_relevant=True,
                is_event_worthy=True,
                article_type="unknown",
                primary_subjects=[],
                mentioned_companies=[],
                mentioned_technologies=[],
                mentioned_countries=[],
                confidence=0.0,
                abstain=True,
                needs_review=True,
                rejection_reason=None,
                reasoning_summary="LLM triage unavailable; deterministic fallback retained.",
                model_name=self.settings.gemini_flash_model,
                prompt_version=call_config.prompt_version,
                schema_version=call_config.schema_version,
                processed_at_utc=processed_at,
            )


def _prompt_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "headline": _resolve_headline(row),
        "source": _resolve_source(row),
        "source_url": str(row.get("source_url") or ""),
        "canonical_url": _coerce_optional_str(row.get("canonical_url")),
        "published_at_utc": _coerce_optional_str(row.get("published_at_utc")),
        "description": _coerce_optional_str(row.get("description")),
        "excerpt": _coerce_optional_str(row.get("excerpt")),
        "discovered_summary_snippet": _coerce_optional_str(row.get("discovered_summary_snippet")),
        "body_text": _coerce_optional_str(row.get("body_text")),
    }


def _resolve_headline(row: dict[str, Any]) -> str:
    for field in ("effective_headline", "title", "discovered_title"):
        value = _coerce_optional_str(row.get(field))
        if value:
            return value
    return "Untitled source article"


def _resolve_source(row: dict[str, Any]) -> str:
    for field in ("effective_source", "site_name", "discovered_source_domain"):
        value = _coerce_optional_str(row.get(field))
        if value:
            return value
    source_url = _coerce_optional_str(row.get("source_url"))
    if not source_url:
        return "unknown"
    parsed = urlparse(source_url)
    return parsed.netloc or "unknown"


def _triage_content_sha(row: dict[str, Any] | pd.Series) -> str:
    if isinstance(row, pd.Series):
        getter = row.get
    else:
        getter = row.get
    content_sha = _coerce_optional_str(getter("content_sha256"))
    if content_sha:
        return content_sha
    payload = "||".join(
        [
            _coerce_optional_str(getter("article_id")) or "",
            _resolve_headline(dict(row)) if isinstance(row, dict) else _resolve_headline(row.to_dict()),
            _coerce_optional_str(getter("description")) or "",
            _coerce_optional_str(getter("excerpt")) or "",
            _coerce_optional_str(getter("body_text")) or "",
            _coerce_optional_str(getter("discovered_summary_snippet")) or "",
        ]
    )
    return sha256_text(payload)


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return 0.0
