from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from semicon_alpha.models.records import LLMJobRunRecord
from semicon_alpha.utils.io import sha256_text, stable_id, upsert_parquet


class LLMJobLogger:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    def log(
        self,
        *,
        workflow: str,
        source_id: str,
        status: str,
        model_name: str,
        prompt_version: str,
        schema_name: str,
        schema_version: str,
        request_payload: dict[str, Any],
        started_at_utc,
        completed_at_utc,
        usage_metadata: dict[str, Any] | None = None,
        response_preview: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        request_hash = sha256_text(json.dumps(request_payload, sort_keys=True))
        usage = usage_metadata or {}
        latency_ms = int((completed_at_utc - started_at_utc).total_seconds() * 1000)
        record = LLMJobRunRecord(
            job_id=stable_id("llmjob", workflow, source_id, completed_at_utc.isoformat(), status),
            workflow=workflow,
            source_id=source_id,
            status=status,
            model_name=model_name,
            prompt_version=prompt_version,
            schema_name=schema_name,
            schema_version=schema_version,
            request_hash=request_hash,
            latency_ms=latency_ms,
            input_token_count=_coerce_int(
                usage.get("promptTokenCount") or usage.get("inputTokenCount")
            ),
            output_token_count=_coerce_int(
                usage.get("candidatesTokenCount") or usage.get("outputTokenCount")
            ),
            cached_input_token_count=_coerce_int(
                usage.get("cachedContentTokenCount") or usage.get("cachedInputTokenCount")
            ),
            error_message=error_message,
            response_preview=response_preview[:500] if response_preview else None,
            metadata_json=metadata or {},
            started_at_utc=started_at_utc,
            completed_at_utc=completed_at_utc,
        )
        upsert_parquet(
            self.output_path,
            [record],
            unique_keys=["job_id"],
            sort_by=["completed_at_utc"],
        )


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None
