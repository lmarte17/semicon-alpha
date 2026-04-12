from datetime import datetime, timedelta, timezone
from pathlib import Path

from semicon_alpha.ingestion.fmp import FMPIngestionService, FMPRequestError
from semicon_alpha.settings import Settings
from semicon_alpha.utils.io import upsert_parquet


class FailingProfileClient:
    def fetch_company_profile(self, symbol):
        raise FMPRequestError("FMP request failed for path /profile with status 403")


class NoopCatalog:
    def refresh_processed_views(self):
        return {"dataset_count": 0}


def test_sync_company_fundamentals_reuses_fresh_cache_on_provider_errors(tmp_path):
    settings = Settings(
        project_root=tmp_path,
        FMP_API_KEY="test-token",
        market_profile_refresh_days=0,
    )
    settings.ensure_directories()
    config_dir = Path(settings.configs_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "universe.yaml").write_text(
        """
companies:
  - ticker: NVDA
    eodhd_symbol: NVDA.US
    company_name: NVIDIA Corporation
    exchange: NASDAQ
    country: United States
    segment_primary: ai_accelerators
    segment_secondary: [networking]
    ecosystem_role: fabless_designer
    market_cap_bucket: mega
    is_origin_name_candidate: true
    notes: Test fixture.
""".strip(),
        encoding="utf-8",
    )
    service = FMPIngestionService(settings, client=FailingProfileClient())
    service.catalog = NoopCatalog()

    fresh_record = {
        "entity_id": "company:NVDA",
        "ticker": "NVDA",
        "eodhd_symbol": "NVDA.US",
        "fetched_at_utc": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "company_name": "NVIDIA Corporation",
        "exchange": "NASDAQ",
        "country": "United States",
        "sector": "Technology",
        "industry": "Semiconductors",
        "description": "GPU company",
        "website": "https://www.nvidia.com",
        "isin": "US67066G1040",
        "lei": None,
        "cik": None,
        "market_capitalization": 1.0,
        "shares_outstanding": 1.0,
        "updated_at": None,
        "raw_json_path": "raw.json",
    }
    upsert_parquet(
        service.fundamentals_path,
        [fresh_record],
        unique_keys=["ticker"],
        sort_by=["fetched_at_utc"],
    )

    companies = service.load_universe()[:1]
    records = service.sync_company_fundamentals(companies)

    assert len(records) == 1
    assert records[0].company_name == "NVIDIA Corporation"
