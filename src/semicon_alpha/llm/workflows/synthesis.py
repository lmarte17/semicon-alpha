from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from semicon_alpha.llm.client import GeminiClient
from semicon_alpha.llm.config import LLMStructuredCallConfig, ModelTier
from semicon_alpha.llm.logging import LLMJobLogger
from semicon_alpha.llm.prompts import (
    COPILOT_SYNTHESIS_PROMPT_VERSION,
    COPILOT_SYNTHESIS_SYSTEM_PROMPT,
    REPORT_SYNTHESIS_PROMPT_VERSION,
    REPORT_SYNTHESIS_SYSTEM_PROMPT,
    render_copilot_synthesis_prompt,
    render_report_synthesis_prompt,
)
from semicon_alpha.llm.schemas import CopilotSynthesisResponse, ReportSynthesisResponse
from semicon_alpha.models.records import CopilotLLMResponseRecord, ReportLLMGenerationRecord
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, stable_id, upsert_parquet


COPILOT_SYNTHESIS_SCHEMA_VERSION = "1"
REPORT_SYNTHESIS_SCHEMA_VERSION = "1"


@dataclass
class CopilotSynthesisResult:
    payload: dict[str, Any]
    record: CopilotLLMResponseRecord


@dataclass
class ReportSynthesisResult:
    payload: dict[str, Any]
    summary: str
    markdown: str
    citations: list[dict[str, Any]]
    record_fields: dict[str, Any]


class AnalystSynthesisService:
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
        self.copilot_output_path = settings.processed_dir / "copilot_llm_responses.parquet"
        self.report_output_path = settings.processed_dir / "report_llm_generations.parquet"

    def synthesize_copilot(
        self,
        *,
        query_text: str,
        scope_type: str,
        scope_id: str | None,
        deterministic_payload: dict[str, Any],
    ) -> dict[str, Any]:
        created_at = now_utc()
        response_id = stable_id("copilotresp", query_text, scope_type, scope_id or "global", created_at.isoformat())
        citations = _attach_citation_ids(deterministic_payload.get("citations", []))
        prompt_payload = {
            "query_text": query_text,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "draft": _compact_payload(
                {
                    "answer": deterministic_payload.get("answer"),
                    "observations": deterministic_payload.get("observations", []),
                    "inferences": deterministic_payload.get("inferences", []),
                    "related_entities": deterministic_payload.get("related_entities", []),
                    "related_events": deterministic_payload.get("related_events", []),
                }
            ),
            "citations": citations,
        }
        prompt = render_copilot_synthesis_prompt(prompt_payload)
        config = LLMStructuredCallConfig(
            workflow="copilot_synthesis",
            prompt_version=COPILOT_SYNTHESIS_PROMPT_VERSION,
            schema_name="CopilotSynthesisResponse",
            schema_version=COPILOT_SYNTHESIS_SCHEMA_VERSION,
            model_tier=_copilot_model_tier(scope_type=scope_type, prompt_length=len(prompt)),
            temperature=0.0,
            max_output_tokens=900,
        )
        attempted_model = self.client.router.resolve_model_name(config)
        request_payload = {
            "query_text": query_text,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "citation_count": len(citations),
        }
        try:
            result = self.client.generate_structured(
                config=config,
                system_prompt=COPILOT_SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=prompt,
                response_model=CopilotSynthesisResponse,
            )
            parsed = CopilotSynthesisResponse.model_validate(result.parsed.model_dump())
            final_payload, synthesis_status, filtered_citations = _finalize_copilot_payload(
                deterministic_payload=deterministic_payload,
                citations=citations,
                parsed=parsed,
            )
            record = CopilotLLMResponseRecord(
                response_id=response_id,
                query_text=query_text,
                scope_type=scope_type,
                scope_id=scope_id,
                answer=final_payload["answer"],
                observations=final_payload["observations"],
                inferences=final_payload["inferences"],
                uncertainties=final_payload["uncertainties"],
                next_checks=final_payload["next_checks"],
                citations_used=[str(item["citation_id"]) for item in filtered_citations],
                related_entity_ids=[str(item["id"]) for item in deterministic_payload.get("related_entities", []) if item.get("id")],
                related_event_ids=[str(item["id"]) for item in deterministic_payload.get("related_events", []) if item.get("id")],
                confidence=round(parsed.confidence, 4),
                abstain=parsed.abstain,
                needs_review=parsed.needs_review,
                synthesis_status=synthesis_status,
                model_name=result.model_name,
                prompt_version=config.prompt_version,
                schema_version=config.schema_version,
                created_at_utc=created_at,
            )
            self.job_logger.log(
                workflow=config.workflow,
                source_id=response_id,
                status="success",
                model_name=result.model_name,
                prompt_version=config.prompt_version,
                schema_name=config.schema_name,
                schema_version=config.schema_version,
                request_payload=request_payload,
                started_at_utc=result.started_at_utc,
                completed_at_utc=result.completed_at_utc,
                usage_metadata=result.raw_response.get("usageMetadata"),
                response_preview=result.raw_text,
                metadata={"scope_type": scope_type, "scope_id": scope_id},
            )
        except Exception as exc:  # pragma: no cover - covered by fallback tests
            self.job_logger.log(
                workflow=config.workflow,
                source_id=response_id,
                status="error",
                model_name=attempted_model,
                prompt_version=config.prompt_version,
                schema_name=config.schema_name,
                schema_version=config.schema_version,
                request_payload=request_payload,
                started_at_utc=created_at,
                completed_at_utc=now_utc(),
                error_message=str(exc),
                metadata={"scope_type": scope_type, "scope_id": scope_id},
            )
            final_payload = _deterministic_copilot_fallback(deterministic_payload)
            record = CopilotLLMResponseRecord(
                response_id=response_id,
                query_text=query_text,
                scope_type=scope_type,
                scope_id=scope_id,
                answer=final_payload["answer"],
                observations=final_payload["observations"],
                inferences=final_payload["inferences"],
                uncertainties=final_payload["uncertainties"],
                next_checks=final_payload["next_checks"],
                citations_used=[str(item["citation_id"]) for item in citations[:4]],
                related_entity_ids=[str(item["id"]) for item in deterministic_payload.get("related_entities", []) if item.get("id")],
                related_event_ids=[str(item["id"]) for item in deterministic_payload.get("related_events", []) if item.get("id")],
                confidence=0.0,
                abstain=True,
                needs_review=True,
                synthesis_status="error_fallback",
                model_name=attempted_model,
                prompt_version=config.prompt_version,
                schema_version=config.schema_version,
                created_at_utc=created_at,
            )
        self._persist_copilot_record(record)
        final_payload["citations"] = [
            {key: value for key, value in item.items() if key != "citation_id"}
            for item in citations_from_ids(citations, record.citations_used)
        ]
        return final_payload

    def synthesize_report(
        self,
        *,
        report_type: str,
        title: str,
        scope_type: str | None,
        scope_id: str | None,
        deterministic_payload: dict[str, Any],
    ) -> ReportSynthesisResult:
        citations = _attach_citation_ids(deterministic_payload.get("citations", []))
        prompt_payload = {
            "report_type": report_type,
            "title": title,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "report_payload": _compact_payload(
                {
                    "summary": deterministic_payload.get("summary"),
                    "sections": deterministic_payload.get("sections", {}),
                    "markdown": deterministic_payload.get("markdown"),
                }
            ),
            "citations": citations,
        }
        prompt = render_report_synthesis_prompt(prompt_payload)
        config = LLMStructuredCallConfig(
            workflow="report_synthesis",
            prompt_version=REPORT_SYNTHESIS_PROMPT_VERSION,
            schema_name="ReportSynthesisResponse",
            schema_version=REPORT_SYNTHESIS_SCHEMA_VERSION,
            model_tier=_report_model_tier(report_type=report_type, prompt_length=len(prompt)),
            temperature=0.0,
            max_output_tokens=2400,
        )
        attempted_model = self.client.router.resolve_model_name(config)
        request_payload = {
            "report_type": report_type,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "citation_count": len(citations),
        }
        created_at = now_utc()
        try:
            result = self.client.generate_structured(
                config=config,
                system_prompt=REPORT_SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=prompt,
                response_model=ReportSynthesisResponse,
            )
            parsed = ReportSynthesisResponse.model_validate(result.parsed.model_dump())
            payload, synthesis_status, filtered_citations = _finalize_report_payload(
                title=title,
                deterministic_payload=deterministic_payload,
                citations=citations,
                parsed=parsed,
            )
            record_fields = {
                "report_type": report_type,
                "title": title,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "summary": payload["summary"],
                "observations": payload["observations"],
                "inferences": payload["inferences"],
                "uncertainties": payload["uncertainties"],
                "next_checks": payload["next_checks"],
                "citations_used": [str(item["citation_id"]) for item in filtered_citations],
                "confidence": round(parsed.confidence, 4),
                "abstain": parsed.abstain,
                "needs_review": parsed.needs_review,
                "synthesis_status": synthesis_status,
                "model_name": result.model_name,
                "prompt_version": config.prompt_version,
                "schema_version": config.schema_version,
                "created_at_utc": created_at,
            }
            self.job_logger.log(
                workflow=config.workflow,
                source_id=report_type,
                status="success",
                model_name=result.model_name,
                prompt_version=config.prompt_version,
                schema_name=config.schema_name,
                schema_version=config.schema_version,
                request_payload=request_payload,
                started_at_utc=result.started_at_utc,
                completed_at_utc=result.completed_at_utc,
                usage_metadata=result.raw_response.get("usageMetadata"),
                response_preview=result.raw_text,
                metadata={"scope_type": scope_type, "scope_id": scope_id},
            )
            return ReportSynthesisResult(
                payload=payload,
                summary=payload["summary"],
                markdown=payload["markdown"],
                citations=[{key: value for key, value in item.items() if key != "citation_id"} for item in filtered_citations],
                record_fields=record_fields,
            )
        except Exception as exc:  # pragma: no cover - covered by fallback tests
            self.job_logger.log(
                workflow=config.workflow,
                source_id=report_type,
                status="error",
                model_name=attempted_model,
                prompt_version=config.prompt_version,
                schema_name=config.schema_name,
                schema_version=config.schema_version,
                request_payload=request_payload,
                started_at_utc=created_at,
                completed_at_utc=now_utc(),
                error_message=str(exc),
                metadata={"scope_type": scope_type, "scope_id": scope_id},
            )
            fallback_payload = _deterministic_report_fallback(title=title, deterministic_payload=deterministic_payload)
            return ReportSynthesisResult(
                payload=fallback_payload,
                summary=fallback_payload["summary"],
                markdown=fallback_payload["markdown"],
                citations=deterministic_payload.get("citations", []),
                record_fields={
                    "report_type": report_type,
                    "title": title,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "summary": fallback_payload["summary"],
                    "observations": fallback_payload["observations"],
                    "inferences": fallback_payload["inferences"],
                    "uncertainties": fallback_payload["uncertainties"],
                    "next_checks": fallback_payload["next_checks"],
                    "citations_used": [str(item["citation_id"]) for item in citations[:6]],
                    "confidence": 0.0,
                    "abstain": True,
                    "needs_review": True,
                    "synthesis_status": "error_fallback",
                    "model_name": attempted_model,
                    "prompt_version": config.prompt_version,
                    "schema_version": config.schema_version,
                    "created_at_utc": created_at,
                },
            )

    def persist_report_generation(
        self,
        *,
        report_id: str,
        result: ReportSynthesisResult,
    ) -> None:
        record = ReportLLMGenerationRecord(
            generation_id=stable_id("reportllm", report_id, result.record_fields["created_at_utc"].isoformat()),
            report_id=report_id,
            **result.record_fields,
        )
        upsert_parquet(
            self.report_output_path,
            [record],
            unique_keys=["generation_id"],
            sort_by=["created_at_utc"],
        )
        self.catalog.refresh_processed_views()

    def _persist_copilot_record(self, record: CopilotLLMResponseRecord) -> None:
        upsert_parquet(
            self.copilot_output_path,
            [record],
            unique_keys=["response_id"],
            sort_by=["created_at_utc"],
        )
        self.catalog.refresh_processed_views()


def _copilot_model_tier(*, scope_type: str, prompt_length: int) -> ModelTier:
    if scope_type in {"scenario", "thesis"} or prompt_length > 8000:
        return ModelTier.PRO
    return ModelTier.FLASH


def _report_model_tier(*, report_type: str, prompt_length: int) -> ModelTier:
    if report_type in {"scenario_memo", "thesis_change_report"} or prompt_length > 9000:
        return ModelTier.PRO
    return ModelTier.FLASH


def _attach_citation_ids(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attached: list[dict[str, Any]] = []
    for index, citation in enumerate(citations[:8], start=1):
        item = dict(citation)
        item["citation_id"] = f"c{index}"
        attached.append(item)
    return attached


def citations_from_ids(citations: list[dict[str, Any]], citation_ids: list[str]) -> list[dict[str, Any]]:
    if not citations:
        return []
    citation_map = {str(item["citation_id"]): item for item in citations if item.get("citation_id")}
    filtered = [citation_map[citation_id] for citation_id in citation_ids if citation_id in citation_map]
    return filtered or citations[:4]


def _finalize_copilot_payload(
    *,
    deterministic_payload: dict[str, Any],
    citations: list[dict[str, Any]],
    parsed: CopilotSynthesisResponse,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    if parsed.abstain or parsed.needs_review or parsed.confidence < 0.65:
        fallback = _deterministic_copilot_fallback(deterministic_payload)
        return fallback, "deterministic_fallback", citations[:4]
    filtered_citations = citations_from_ids(citations, parsed.citations_used)
    payload = {
        "answer": parsed.answer.strip(),
        "observations": _bounded_list(parsed.observations, fallback=deterministic_payload.get("observations", [])),
        "inferences": _bounded_list(parsed.inferences, fallback=deterministic_payload.get("inferences", [])),
        "uncertainties": _bounded_list(parsed.uncertainties),
        "next_checks": _bounded_list(parsed.next_checks),
        "citations": filtered_citations,
        "related_entities": deterministic_payload.get("related_entities", []),
        "related_events": deterministic_payload.get("related_events", []),
    }
    return payload, "synthesized", filtered_citations


def _finalize_report_payload(
    *,
    title: str,
    deterministic_payload: dict[str, Any],
    citations: list[dict[str, Any]],
    parsed: ReportSynthesisResponse,
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    if parsed.abstain or parsed.needs_review or parsed.confidence < 0.65:
        fallback = _deterministic_report_fallback(title=title, deterministic_payload=deterministic_payload)
        return fallback, "deterministic_fallback", citations[:6]
    filtered_citations = citations_from_ids(citations, parsed.citations_used)
    observations = _bounded_list(parsed.observations)
    inferences = _bounded_list(parsed.inferences)
    uncertainties = _bounded_list(parsed.uncertainties)
    next_checks = _bounded_list(parsed.next_checks)
    summary = parsed.summary.strip() or str(deterministic_payload.get("summary") or "")
    markdown_parts = [f"# {title}", "", summary]
    if observations:
        markdown_parts.extend(["", "## Observations", *[f"- {item}" for item in observations]])
    if inferences:
        markdown_parts.extend(["", "## Inferences", *[f"- {item}" for item in inferences]])
    if uncertainties:
        markdown_parts.extend(["", "## Uncertainties", *[f"- {item}" for item in uncertainties]])
    if next_checks:
        markdown_parts.extend(["", "## Next Checks", *[f"- {item}" for item in next_checks]])
    markdown_parts.extend(["", parsed.markdown_body.strip()])
    payload = {
        "summary": summary,
        "observations": observations,
        "inferences": inferences,
        "uncertainties": uncertainties,
        "next_checks": next_checks,
        "markdown": "\n".join(part for part in markdown_parts if part is not None),
        "citations": [{key: value for key, value in item.items() if key != "citation_id"} for item in filtered_citations],
    }
    return payload, "synthesized", filtered_citations


def _deterministic_copilot_fallback(deterministic_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": str(deterministic_payload.get("answer") or ""),
        "observations": _bounded_list(deterministic_payload.get("observations", [])),
        "inferences": _bounded_list(deterministic_payload.get("inferences", [])),
        "uncertainties": [],
        "next_checks": [],
        "citations": deterministic_payload.get("citations", [])[:4],
        "related_entities": deterministic_payload.get("related_entities", []),
        "related_events": deterministic_payload.get("related_events", []),
    }


def _deterministic_report_fallback(*, title: str, deterministic_payload: dict[str, Any]) -> dict[str, Any]:
    summary = str(deterministic_payload.get("summary") or "")
    markdown = str(deterministic_payload.get("markdown") or f"# {title}\n\n{summary}")
    return {
        "summary": summary,
        "observations": [],
        "inferences": [],
        "uncertainties": [],
        "next_checks": [],
        "markdown": markdown,
        "citations": deterministic_payload.get("citations", [])[:6],
    }


def _bounded_list(values: list[str] | None, fallback: list[str] | None = None) -> list[str]:
    source = values if values else (fallback or [])
    cleaned: list[str] = []
    for value in source:
        text = str(value).strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:6]


def _compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            compact[key] = value[:3000]
        elif isinstance(value, list):
            compact[key] = value[:8]
        elif isinstance(value, dict):
            compact[key] = {inner_key: inner_value for inner_key, inner_value in list(value.items())[:12]}
        else:
            compact[key] = value
    return compact
