from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from semicon_alpha.llm.config import LLMStructuredCallConfig
from semicon_alpha.llm.router import GeminiModelRouter
from semicon_alpha.settings import Settings
from semicon_alpha.utils.io import now_utc


SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass
class StructuredGenerationResult:
    parsed: BaseModel
    model_name: str
    raw_text: str
    raw_response: dict[str, Any]
    usage_metadata: dict[str, Any]
    started_at_utc: datetime
    completed_at_utc: datetime


class GeminiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.http_client = http_client
        self.router = GeminiModelRouter(settings)

    def generate_structured(
        self,
        *,
        config: LLMStructuredCallConfig,
        system_prompt: str,
        user_prompt: str,
        response_model: type[SchemaT],
        escalate: bool = False,
    ) -> StructuredGenerationResult:
        api_key = self.settings.require_gemini_api_key()
        model_name = self.router.resolve_model_name(config, escalate=escalate)
        started_at = now_utc()

        payload = {
            "system_instruction": {
                "parts": [
                    {
                        "text": system_prompt,
                    }
                ]
            },
            "contents": [
                {
                    "parts": [
                        {
                            "text": user_prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": config.temperature,
                "responseMimeType": config.response_mime_type,
                "responseSchema": _sanitize_response_schema(response_model.model_json_schema()),
            },
        }
        if config.max_output_tokens is not None:
            payload["generationConfig"]["maxOutputTokens"] = config.max_output_tokens

        url = f"{self.settings.gemini_base_url}/models/{model_name}:generateContent"
        response_json = self._post_json(
            url=url,
            payload=payload,
            api_key=api_key,
        )
        raw_text = _extract_response_text(response_json)
        try:
            parsed_payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Gemini response was not valid JSON: {raw_text[:300]}") from exc
        parsed = response_model.model_validate(parsed_payload)
        completed_at = now_utc()
        usage_metadata = response_json.get("usageMetadata") or {}
        return StructuredGenerationResult(
            parsed=parsed,
            model_name=model_name,
            raw_text=raw_text,
            raw_response=response_json,
            usage_metadata=usage_metadata,
            started_at_utc=started_at,
            completed_at_utc=completed_at,
        )

    def _post_json(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any]:
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        if self.http_client is not None:
            response = self.http_client.post(url, headers=headers, json=payload)
            _raise_for_status_with_body(response)
            return response.json()

        with httpx.Client(timeout=self.settings.gemini_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            _raise_for_status_with_body(response)
            return response.json()


def _extract_response_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        prompt_feedback = payload.get("promptFeedback")
        raise RuntimeError(f"Gemini returned no candidates: {prompt_feedback}")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text_parts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    response_text = "\n".join(part for part in text_parts if part).strip()
    if not response_text:
        raise RuntimeError("Gemini response did not contain text parts.")
    return response_text


def _sanitize_response_schema(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"additionalProperties", "title", "default", "examples"}:
                continue
            sanitized[key] = _sanitize_response_schema(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_response_schema(item) for item in value]
    return value


def _raise_for_status_with_body(response: httpx.Response) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:  # pragma: no cover - exercised in live failures
        message = response.text.strip()
        if message:
            raise RuntimeError(
                f"Gemini request failed with status {response.status_code}: {message}"
            ) from exc
        raise
