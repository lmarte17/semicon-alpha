from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ModelTier(StrEnum):
    FLASH = "flash"
    PRO = "pro"


class LLMStructuredCallConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: str
    prompt_version: str
    schema_name: str
    schema_version: str
    model_name: str | None = None
    model_tier: ModelTier = ModelTier.FLASH
    temperature: float = 0.0
    max_output_tokens: int | None = None
    response_mime_type: str = "application/json"
