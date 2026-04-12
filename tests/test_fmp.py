from datetime import date, datetime
from pathlib import Path

from semicon_alpha.ingestion.fmp import (
    FMPClient,
    FMPIngestionService,
    build_price_sync_windows,
    normalize_provider_symbol,
)
from semicon_alpha.settings import Settings


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if "/historical-price-eod/full" in url:
            return FakeResponse(
                [
                    {
                        "date": "2026-04-01",
                        "open": 1,
                        "high": 2,
                        "low": 0.5,
                        "close": 1.5,
                        "adjClose": 1.4,
                        "volume": 10,
                    }
                ]
            )
        if "/profile" in url:
            return FakeResponse([{"companyName": "NVIDIA Corporation"}])
        raise AssertionError(f"Unexpected URL: {url}")


def test_fmp_client_uses_expected_paths():
    settings = Settings(FMP_API_KEY="test-token")
    client = FMPClient(settings=settings, client=FakeClient())
    prices = client.fetch_eod_prices("NVDA.US", start="2026-04-01", end="2026-04-02")
    profile = client.fetch_company_profile("NVDA.US")

    assert prices[0]["close"] == 1.5
    assert profile["companyName"] == "NVIDIA Corporation"


def test_normalize_provider_symbol_strips_exchange_suffixes_only():
    assert normalize_provider_symbol("NVDA.US") == "NVDA"
    assert normalize_provider_symbol("BRK.B") == "BRK.B"


def test_build_price_sync_windows_skips_same_day_refetch():
    windows = build_price_sync_windows(
        state={
            "min_trade_date": date(2026, 4, 1),
            "max_trade_date": date(2026, 4, 10),
            "last_fetched_at_utc": datetime(2026, 4, 12, 14, 0, 0),
        },
        requested_start=date(2026, 4, 1),
        requested_end=None,
        today=date(2026, 4, 12),
    )
    assert windows == []


class NoopCatalog:
    def refresh_processed_views(self):
        return {"dataset_count": 0}


def test_sync_exchange_symbols_uses_curated_universe_directory(tmp_path):
    settings = Settings(project_root=tmp_path, FMP_API_KEY="test-token")
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
    (config_dir / "benchmarks.yaml").write_text("benchmarks: []\n", encoding="utf-8")
    service = FMPIngestionService(settings=settings, client=FakeClient())
    service.catalog = NoopCatalog()

    records = service.sync_exchange_symbols({"NASDAQ"})

    assert len(records) == 1
    assert records[0].exchange_code == "NASDAQ"
    assert records[0].code == "NVDA"
