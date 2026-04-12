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
    def outputs_dir(self) -> Path:
        return self.project_root / "outputs"

    @property
    def configs_dir(self) -> Path:
        return self.project_root / "configs"

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
