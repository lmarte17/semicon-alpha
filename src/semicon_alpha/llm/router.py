from __future__ import annotations

from semicon_alpha.llm.config import LLMStructuredCallConfig, ModelTier
from semicon_alpha.settings import Settings


class GeminiModelRouter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def resolve_model_name(
        self,
        config: LLMStructuredCallConfig,
        *,
        escalate: bool = False,
    ) -> str:
        if config.model_name:
            return config.model_name
        if escalate or config.model_tier == ModelTier.PRO:
            return self.settings.gemini_pro_model
        return self.settings.gemini_flash_model
