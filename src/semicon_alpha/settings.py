from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from semicon_alpha.utils.io import discover_project_root


class Settings(BaseSettings):
    project_root: Path = Field(default_factory=discover_project_root)
    lithos_url: str = "https://lithosgraphein.com/"
    request_timeout_seconds: float = 30.0
    request_pause_seconds: float = 0.2
    user_agent: str = "semicon-alpha/0.1 (semiconductor ingestion engine)"
    fmp_base_url: str = "https://financialmodelingprep.com/stable"
    fmp_api_key: str | None = Field(default=None, alias="FMP_API_KEY")
    market_profile_refresh_days: int = 7
    llm_enabled: bool = Field(default=True, alias="LLM_ENABLED")
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_flash_model: str = Field(
        default="gemini-3.1-flash-lite-preview",
        alias="GEMINI_FLASH_MODEL",
    )
    gemini_pro_model: str = Field(
        default="gemini-3.1-pro-preview",
        alias="GEMINI_PRO_MODEL",
    )
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001",
        alias="GEMINI_EMBEDDING_MODEL",
    )
    gemini_timeout_seconds: float = 45.0
    llm_article_triage_min_confidence: float = 0.7
    llm_event_review_min_confidence: float = 0.72
    llm_event_review_override_confidence: float = 0.84
    gemini_embedding_output_dimensionality: int = 256
    llm_retrieval_chunk_chars: int = 1800
    llm_retrieval_chunk_overlap_chars: int = 250

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def reference_dir(self) -> Path:
        return self.data_dir / "reference"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "semicon_alpha.duckdb"

    @property
    def appstate_path(self) -> Path:
        return self.data_dir / "app_state.sqlite"

    @property
    def outputs_dir(self) -> Path:
        return self.project_root / "outputs"

    @property
    def configs_dir(self) -> Path:
        return self.project_root / "configs"

    @property
    def llm_runtime_enabled(self) -> bool:
        return self.llm_enabled and bool(self.gemini_api_key)

    def ensure_directories(self) -> None:
        for directory in (
            self.data_dir,
            self.raw_dir,
            self.processed_dir,
            self.reference_dir,
            self.outputs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def require_fmp_api_key(self) -> str:
        if not self.fmp_api_key:
            raise RuntimeError(
                "FMP_API_KEY is not configured. Set it in the environment or .env."
            )
        return self.fmp_api_key

    def require_gemini_api_key(self) -> str:
        if not self.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Set it in the environment or .env."
            )
        return self.gemini_api_key
