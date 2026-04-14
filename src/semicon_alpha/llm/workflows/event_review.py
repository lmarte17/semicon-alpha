from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from semicon_alpha.llm.client import GeminiClient
from semicon_alpha.llm.config import LLMStructuredCallConfig, ModelTier
from semicon_alpha.llm.logging import LLMJobLogger
from semicon_alpha.llm.prompts import (
    EVENT_REVIEW_PROMPT_VERSION,
    EVENT_REVIEW_SYSTEM_PROMPT,
    render_event_review_prompt,
)
from semicon_alpha.llm.schemas import EventReviewResponse
from semicon_alpha.models.records import (
    EventLLMEntityRecord,
    EventLLMFusionDecisionRecord,
    EventLLMReviewRecord,
    EventLLMThemeRecord,
)
from semicon_alpha.settings import Settings
from semicon_alpha.utils.io import now_utc, stable_id


EVENT_REVIEW_SCHEMA_VERSION = "1"


@dataclass
class EventReviewServiceResult:
    review_record: EventLLMReviewRecord
    entity_records: list[EventLLMEntityRecord]
    theme_records: list[EventLLMThemeRecord]
    fusion_record: EventLLMFusionDecisionRecord
    final_event_type: str
    final_direction: str
    final_severity: str
    final_summary: str | None
    final_reasoning: str | None
    final_origin_companies: list[str]
    final_mentioned_companies: list[str]
    final_primary_segment: str | None
    final_secondary_segments: list[str]
    final_primary_theme_ids: list[str]
    extraction_method: str
    llm_review_status: str
    evidence_spans: list[str]
    uncertainty_flags: list[str]
    review_notes: str | None


class EventReviewService:
    def __init__(
        self,
        settings: Settings,
        *,
        client: GeminiClient | None = None,
        job_logger: LLMJobLogger | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or GeminiClient(settings)
        self.job_logger = job_logger or LLMJobLogger(settings.processed_dir / "llm_job_runs.parquet")

    def review(
        self,
        *,
        event_id: str,
        article: dict[str, Any],
        deterministic: dict[str, Any],
        classification_candidates: list[dict[str, Any]],
        tracked_companies: dict[str, str],
        theme_names: dict[str, str],
    ) -> EventReviewServiceResult:
        processed_at = now_utc()
        prompt_payload = {
            "article": article,
            "deterministic": deterministic,
            "classification_candidates": classification_candidates,
            "tracked_companies": [
                f"{ticker}: {company_name}" for ticker, company_name in sorted(tracked_companies.items())
            ],
            "allowed_themes": [
                f"{theme_id}: {theme_name}" for theme_id, theme_name in sorted(theme_names.items())
            ],
        }
        prompt = render_event_review_prompt(prompt_payload)
        request_payload = {
            "system_prompt": EVENT_REVIEW_SYSTEM_PROMPT,
            "user_prompt": prompt,
            "article_id": str(article["article_id"]),
            "event_id": event_id,
        }
        call_config = LLMStructuredCallConfig(
            workflow="event_review",
            prompt_version=EVENT_REVIEW_PROMPT_VERSION,
            schema_name="EventReviewResponse",
            schema_version=EVENT_REVIEW_SCHEMA_VERSION,
            model_tier=ModelTier.FLASH,
            temperature=0.0,
            max_output_tokens=900,
        )
        try:
            result = self.client.generate_structured(
                config=call_config,
                system_prompt=EVENT_REVIEW_SYSTEM_PROMPT,
                user_prompt=prompt,
                response_model=EventReviewResponse,
            )
            parsed = EventReviewResponse.model_validate(result.parsed.model_dump())
            disagreement_flags = _disagreement_flags(parsed=parsed, deterministic=deterministic)

            if _should_escalate(settings=self.settings, parsed=parsed, disagreement_flags=disagreement_flags, deterministic=deterministic):
                result = self.client.generate_structured(
                    config=call_config,
                    system_prompt=EVENT_REVIEW_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    response_model=EventReviewResponse,
                    escalate=True,
                )
                parsed = EventReviewResponse.model_validate(result.parsed.model_dump())
                disagreement_flags = _disagreement_flags(parsed=parsed, deterministic=deterministic)

            self.job_logger.log(
                workflow=call_config.workflow,
                source_id=event_id,
                status="success",
                model_name=result.model_name,
                prompt_version=call_config.prompt_version,
                schema_name=call_config.schema_name,
                schema_version=call_config.schema_version,
                request_payload=request_payload,
                started_at_utc=result.started_at_utc,
                completed_at_utc=result.completed_at_utc,
                usage_metadata=result.raw_response.get("usageMetadata"),
                response_preview=result.raw_text,
                metadata={"article_id": str(article["article_id"])},
            )
            return _build_review_result(
                settings=self.settings,
                event_id=event_id,
                article=article,
                deterministic=deterministic,
                parsed=parsed,
                disagreement_flags=disagreement_flags,
                theme_names=theme_names,
                tracked_companies=tracked_companies,
                model_name=result.model_name,
                prompt_version=call_config.prompt_version,
                schema_version=call_config.schema_version,
                processed_at=processed_at,
            )
        except Exception as exc:  # pragma: no cover - covered via fallback tests
            self.job_logger.log(
                workflow=call_config.workflow,
                source_id=event_id,
                status="error",
                model_name=self.settings.gemini_flash_model,
                prompt_version=call_config.prompt_version,
                schema_name=call_config.schema_name,
                schema_version=call_config.schema_version,
                request_payload=request_payload,
                started_at_utc=processed_at,
                completed_at_utc=now_utc(),
                error_message=str(exc),
                metadata={"article_id": str(article["article_id"])},
            )
            return _fallback_result(
                event_id=event_id,
                article=article,
                deterministic=deterministic,
                processed_at=processed_at,
                model_name=self.settings.gemini_flash_model,
                prompt_version=call_config.prompt_version,
                schema_version=call_config.schema_version,
                note="LLM event review unavailable; deterministic extraction retained.",
            )


def _build_review_result(
    *,
    settings: Settings,
    event_id: str,
    article: dict[str, Any],
    deterministic: dict[str, Any],
    parsed: EventReviewResponse,
    disagreement_flags: list[str],
    theme_names: dict[str, str],
    tracked_companies: dict[str, str],
    model_name: str,
    prompt_version: str,
    schema_version: str,
    processed_at,
) -> EventReviewServiceResult:
    deterministic_confidence = _coerce_float(deterministic.get("confidence"))
    llm_confidence = float(parsed.confidence)
    high_confidence = (
        not parsed.abstain
        and not parsed.needs_review
        and llm_confidence >= settings.llm_event_review_min_confidence
    )
    allow_override = (
        high_confidence
        and disagreement_flags
        and deterministic_confidence < settings.llm_event_review_min_confidence
        and llm_confidence >= settings.llm_event_review_override_confidence
    )

    deterministic_origin = _normalize_tickers(deterministic.get("origin_companies"))
    deterministic_mentioned = _normalize_tickers(deterministic.get("mentioned_companies"))
    deterministic_theme_ids = _normalize_theme_ids(
        deterministic.get("primary_theme_ids") or deterministic.get("primary_themes"),
        theme_names,
    )

    llm_origin = _filter_tracked_tickers(parsed.suggested_origin_companies, tracked_companies)
    llm_mentioned = _filter_tracked_tickers(parsed.suggested_mentioned_companies, tracked_companies)
    llm_primary_theme_ids = _normalize_theme_ids(parsed.suggested_primary_theme_ids, theme_names)
    llm_secondary_theme_ids = _normalize_theme_ids(parsed.suggested_secondary_theme_ids, theme_names)

    final_event_type = str(deterministic.get("event_type"))
    final_direction = str(deterministic.get("direction"))
    final_severity = str(deterministic.get("severity"))
    extraction_method = "deterministic"
    llm_review_status = "reviewed"
    decision = "deterministic_retained"

    if parsed.abstain:
        llm_review_status = "abstained"
        decision = "deterministic_fallback"
    elif parsed.needs_review or llm_confidence < settings.llm_event_review_min_confidence:
        llm_review_status = "needs_review"
        decision = "deterministic_fallback"
    elif allow_override:
        final_event_type = parsed.selected_event_type or final_event_type
        final_direction = parsed.selected_direction or final_direction
        final_severity = parsed.selected_severity or final_severity
        extraction_method = "deterministic_plus_llm_override"
        llm_review_status = "override_applied"
        decision = "llm_override"
    else:
        extraction_method = "deterministic_plus_llm_review"
        if disagreement_flags:
            llm_review_status = "disagreement"
            decision = "deterministic_retained"
        else:
            decision = "llm_enrichment"

    final_origin_companies = deterministic_origin
    final_mentioned_companies = deterministic_mentioned
    final_primary_segment = _coerce_optional_str(deterministic.get("primary_segment"))
    final_secondary_segments = _normalize_strings(deterministic.get("secondary_segments"))
    final_primary_theme_ids = deterministic_theme_ids
    final_summary = _coerce_optional_str(deterministic.get("summary"))
    final_reasoning = _coerce_optional_str(deterministic.get("reasoning"))

    if high_confidence:
        if allow_override or not final_origin_companies:
            final_origin_companies = _ordered_union(llm_origin, final_origin_companies)
        final_mentioned_companies = _ordered_union(
            deterministic_mentioned,
            llm_origin,
            llm_mentioned,
        )
        if allow_override and parsed.suggested_primary_segment:
            final_primary_segment = parsed.suggested_primary_segment
        elif not final_primary_segment:
            final_primary_segment = parsed.suggested_primary_segment
        final_secondary_segments = _ordered_union(
            final_secondary_segments,
            parsed.suggested_secondary_segments,
        )
        if allow_override and llm_primary_theme_ids:
            final_primary_theme_ids = _ordered_union(llm_primary_theme_ids, llm_secondary_theme_ids)
        else:
            final_primary_theme_ids = _ordered_union(
                deterministic_theme_ids,
                llm_primary_theme_ids,
                llm_secondary_theme_ids,
            )
        if parsed.summary:
            final_summary = parsed.summary
        final_reasoning = _merge_reasoning(
            deterministic_reasoning=_coerce_optional_str(deterministic.get("reasoning")),
            llm_reasoning=parsed.reasoning_summary,
        )

    review_notes = parsed.review_notes
    if disagreement_flags:
        disagreement_note = f"Disagreement: {', '.join(disagreement_flags)}."
        review_notes = " ".join(part for part in [review_notes, disagreement_note] if part).strip()

    review_record = EventLLMReviewRecord(
        event_id=event_id,
        article_id=str(article["article_id"]),
        deterministic_event_type=str(deterministic.get("event_type")),
        llm_event_type=parsed.selected_event_type,
        deterministic_direction=str(deterministic.get("direction")),
        llm_direction=parsed.selected_direction,
        deterministic_severity=str(deterministic.get("severity")),
        llm_severity=parsed.selected_severity,
        llm_summary=parsed.summary,
        llm_reasoning_summary=parsed.reasoning_summary,
        confidence=round(llm_confidence, 4),
        abstain=parsed.abstain,
        needs_review=parsed.needs_review,
        disagreement_flags=disagreement_flags,
        evidence_spans=parsed.evidence_spans[:6],
        uncertainty_flags=parsed.uncertainty_flags[:6],
        time_horizon_hint=parsed.time_horizon_hint,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        processed_at_utc=processed_at,
    )

    entity_records = _build_entity_records(
        event_id=event_id,
        article_id=str(article["article_id"]),
        parsed=parsed,
        tracked_companies=tracked_companies,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        processed_at=processed_at,
    )
    theme_records = _build_theme_records(
        event_id=event_id,
        article_id=str(article["article_id"]),
        parsed=parsed,
        theme_names=theme_names,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        processed_at=processed_at,
    )
    fusion_record = EventLLMFusionDecisionRecord(
        event_id=event_id,
        article_id=str(article["article_id"]),
        deterministic_event_type=str(deterministic.get("event_type")),
        llm_event_type=parsed.selected_event_type,
        final_event_type=final_event_type,
        deterministic_direction=str(deterministic.get("direction")),
        llm_direction=parsed.selected_direction,
        final_direction=final_direction,
        deterministic_severity=str(deterministic.get("severity")),
        llm_severity=parsed.selected_severity,
        final_severity=final_severity,
        decision=decision,
        extraction_method=extraction_method,
        llm_review_status=llm_review_status,
        disagreement_flags=disagreement_flags,
        deterministic_confidence=round(deterministic_confidence, 4),
        llm_confidence=round(llm_confidence, 4),
        review_notes=review_notes,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        processed_at_utc=processed_at,
    )
    return EventReviewServiceResult(
        review_record=review_record,
        entity_records=entity_records,
        theme_records=theme_records,
        fusion_record=fusion_record,
        final_event_type=final_event_type,
        final_direction=final_direction,
        final_severity=final_severity,
        final_summary=final_summary,
        final_reasoning=final_reasoning,
        final_origin_companies=final_origin_companies[:8],
        final_mentioned_companies=final_mentioned_companies[:12],
        final_primary_segment=final_primary_segment,
        final_secondary_segments=final_secondary_segments[:6],
        final_primary_theme_ids=final_primary_theme_ids[:4],
        extraction_method=extraction_method,
        llm_review_status=llm_review_status,
        evidence_spans=parsed.evidence_spans[:6],
        uncertainty_flags=parsed.uncertainty_flags[:6],
        review_notes=review_notes,
    )


def _fallback_result(
    *,
    event_id: str,
    article: dict[str, Any],
    deterministic: dict[str, Any],
    processed_at,
    model_name: str,
    prompt_version: str,
    schema_version: str,
    note: str,
) -> EventReviewServiceResult:
    review_record = EventLLMReviewRecord(
        event_id=event_id,
        article_id=str(article["article_id"]),
        deterministic_event_type=str(deterministic.get("event_type")),
        llm_event_type=None,
        deterministic_direction=str(deterministic.get("direction")),
        llm_direction=None,
        deterministic_severity=str(deterministic.get("severity")),
        llm_severity=None,
        llm_summary=None,
        llm_reasoning_summary=note,
        confidence=0.0,
        abstain=True,
        needs_review=True,
        disagreement_flags=[],
        evidence_spans=[],
        uncertainty_flags=["llm_unavailable"],
        time_horizon_hint=None,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        processed_at_utc=processed_at,
    )
    fusion_record = EventLLMFusionDecisionRecord(
        event_id=event_id,
        article_id=str(article["article_id"]),
        deterministic_event_type=str(deterministic.get("event_type")),
        llm_event_type=None,
        final_event_type=str(deterministic.get("event_type")),
        deterministic_direction=str(deterministic.get("direction")),
        llm_direction=None,
        final_direction=str(deterministic.get("direction")),
        deterministic_severity=str(deterministic.get("severity")),
        llm_severity=None,
        final_severity=str(deterministic.get("severity")),
        decision="deterministic_fallback",
        extraction_method="deterministic",
        llm_review_status="error",
        disagreement_flags=[],
        deterministic_confidence=round(_coerce_float(deterministic.get("confidence")), 4),
        llm_confidence=0.0,
        review_notes=note,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        processed_at_utc=processed_at,
    )
    return EventReviewServiceResult(
        review_record=review_record,
        entity_records=[],
        theme_records=[],
        fusion_record=fusion_record,
        final_event_type=str(deterministic.get("event_type")),
        final_direction=str(deterministic.get("direction")),
        final_severity=str(deterministic.get("severity")),
        final_summary=_coerce_optional_str(deterministic.get("summary")),
        final_reasoning=_coerce_optional_str(deterministic.get("reasoning")),
        final_origin_companies=_normalize_tickers(deterministic.get("origin_companies")),
        final_mentioned_companies=_normalize_tickers(deterministic.get("mentioned_companies")),
        final_primary_segment=_coerce_optional_str(deterministic.get("primary_segment")),
        final_secondary_segments=_normalize_strings(deterministic.get("secondary_segments")),
        final_primary_theme_ids=[],
        extraction_method="deterministic",
        llm_review_status="error",
        evidence_spans=[],
        uncertainty_flags=["llm_unavailable"],
        review_notes=note,
    )


def _build_entity_records(
    *,
    event_id: str,
    article_id: str,
    parsed: EventReviewResponse,
    tracked_companies: dict[str, str],
    model_name: str,
    prompt_version: str,
    schema_version: str,
    processed_at,
) -> list[EventLLMEntityRecord]:
    rows: list[tuple[str | None, str, str, str]] = []
    rows.extend((f"company:{ticker}", ticker, "company", "origin") for ticker in _filter_tracked_tickers(parsed.suggested_origin_companies, tracked_companies))
    rows.extend((f"company:{ticker}", ticker, "company", "affected") for ticker in _filter_tracked_tickers(parsed.suggested_mentioned_companies, tracked_companies))
    rows.extend((None, item, "regulator", "regulator") for item in _normalize_strings(parsed.suggested_regulators))
    rows.extend((None, item, "country", "country") for item in _normalize_strings(parsed.suggested_countries))
    rows.extend((None, item, "technology", "technology") for item in _normalize_strings(parsed.suggested_technologies))
    rows.extend((None, item, "facility", "facility") for item in _normalize_strings(parsed.suggested_facilities))

    records: list[EventLLMEntityRecord] = []
    seen: set[tuple[str, str]] = set()
    for entity_id, entity_name, entity_type, role_label in rows:
        key = (entity_type, entity_name.lower())
        if key in seen:
            continue
        seen.add(key)
        records.append(
            EventLLMEntityRecord(
                review_item_id=stable_id("eventllmentity", event_id, entity_type, entity_name, role_label),
                event_id=event_id,
                article_id=article_id,
                entity_id=entity_id,
                entity_name=entity_name,
                entity_type=entity_type,
                role_label=role_label,
                evidence_snippets=parsed.evidence_spans[:4],
                confidence=round(parsed.confidence, 4),
                model_name=model_name,
                prompt_version=prompt_version,
                schema_version=schema_version,
                processed_at_utc=processed_at,
            )
        )
    return records


def _build_theme_records(
    *,
    event_id: str,
    article_id: str,
    parsed: EventReviewResponse,
    theme_names: dict[str, str],
    model_name: str,
    prompt_version: str,
    schema_version: str,
    processed_at,
) -> list[EventLLMThemeRecord]:
    records: list[EventLLMThemeRecord] = []
    for role_label, theme_ids in (
        ("primary_theme", _normalize_theme_ids(parsed.suggested_primary_theme_ids, theme_names)),
        ("secondary_theme", _normalize_theme_ids(parsed.suggested_secondary_theme_ids, theme_names)),
    ):
        for theme_id in theme_ids:
            records.append(
                EventLLMThemeRecord(
                    review_item_id=stable_id("eventllmtheme", event_id, role_label, theme_id),
                    event_id=event_id,
                    article_id=article_id,
                    theme_id=theme_id,
                    theme_name=theme_names.get(theme_id, theme_id),
                    role_label=role_label,
                    evidence_snippets=parsed.evidence_spans[:4],
                    confidence=round(parsed.confidence, 4),
                    model_name=model_name,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    processed_at_utc=processed_at,
                )
            )
    return records


def _should_escalate(
    *,
    settings: Settings,
    parsed: EventReviewResponse,
    disagreement_flags: list[str],
    deterministic: dict[str, Any],
) -> bool:
    if parsed.abstain or parsed.needs_review:
        return True
    deterministic_confidence = _coerce_float(deterministic.get("confidence"))
    if disagreement_flags and deterministic_confidence < settings.llm_event_review_override_confidence:
        return True
    return parsed.confidence < settings.llm_event_review_min_confidence and deterministic_confidence < settings.llm_event_review_min_confidence


def _disagreement_flags(*, parsed: EventReviewResponse, deterministic: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if parsed.selected_event_type and parsed.selected_event_type != str(deterministic.get("event_type")):
        flags.append("event_type")
    if parsed.selected_direction and parsed.selected_direction != str(deterministic.get("direction")):
        flags.append("direction")
    if parsed.selected_severity and parsed.selected_severity != str(deterministic.get("severity")):
        flags.append("severity")

    deterministic_origin = set(_normalize_tickers(deterministic.get("origin_companies")))
    llm_origin = set(_normalize_tickers(parsed.suggested_origin_companies))
    if llm_origin and deterministic_origin and llm_origin != deterministic_origin:
        flags.append("origin_companies")

    deterministic_theme_ids = set(_normalize_strings(deterministic.get("primary_theme_ids") or deterministic.get("primary_themes")))
    llm_theme_ids = set(_normalize_strings(parsed.suggested_primary_theme_ids))
    if llm_theme_ids and deterministic_theme_ids and llm_theme_ids != deterministic_theme_ids:
        flags.append("primary_themes")
    return flags


def _filter_tracked_tickers(values: list[str] | None, tracked_companies: dict[str, str]) -> list[str]:
    if not values:
        return []
    allowed = {ticker.upper(): ticker.upper() for ticker in tracked_companies}
    normalized: list[str] = []
    for value in values:
        ticker = str(value).strip().upper()
        if ticker and ticker in allowed and ticker not in normalized:
            normalized.append(ticker)
    return normalized


def _normalize_tickers(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    return [str(value).strip().upper() for value in values if str(value).strip()]


def _normalize_strings(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_theme_ids(values: Any, theme_names: dict[str, str]) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    valid_ids = {theme_id.lower(): theme_id for theme_id in theme_names}
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        resolved = valid_ids.get(text.lower())
        if resolved and resolved not in normalized:
            normalized.append(resolved)
    return normalized


def _ordered_union(*groups: list[str]) -> list[str]:
    values: list[str] = []
    for group in groups:
        for value in group:
            if value and value not in values:
                values.append(value)
    return values


def _merge_reasoning(*, deterministic_reasoning: str | None, llm_reasoning: str | None) -> str | None:
    parts = [part.strip() for part in [llm_reasoning, deterministic_reasoning] if part and part.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} Deterministic context: {parts[1]}"


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
