from semicon_alpha.ingestion.reference import ReferenceDataService
from semicon_alpha.models.records import CompanyFundamentalRecord
from semicon_alpha.settings import Settings


class FakeMarketService:
    def __init__(self, settings):
        self.settings = settings

    def load_universe(self):
        from semicon_alpha.ingestion.fmp import FMPIngestionService

        return FMPIngestionService(self.settings).load_universe()

    def sync_exchange_symbols(self, exchange_codes):
        return []

    def sync_company_fundamentals(self, companies):
        return [
            CompanyFundamentalRecord(
                entity_id="company:NVDA",
                ticker="NVDA",
                eodhd_symbol="NVDA.US",
                fetched_at_utc="2026-04-12T00:00:00+00:00",
                company_name="NVIDIA Corporation",
                exchange="NASDAQ",
                country="United States",
                sector="Technology",
                industry="Semiconductors",
                description="GPU company",
                website="https://www.nvidia.com",
                isin="US67066G1040",
                lei=None,
                cik=None,
                market_capitalization=1.0,
                shares_outstanding=1.0,
                updated_at=None,
                raw_json_path="raw.json",
            )
        ]


def test_reference_service_builds_company_registry():
    settings = Settings()
    service = ReferenceDataService(settings, FakeMarketService(settings))
    companies = service.market_service.load_universe()
    fundamentals = [
        CompanyFundamentalRecord(
            entity_id="company:NVDA",
            ticker="NVDA",
            eodhd_symbol="NVDA.US",
            fetched_at_utc="2026-04-12T00:00:00+00:00",
            company_name="NVIDIA Corporation",
            exchange="NASDAQ",
            country="United States",
            sector="Technology",
            industry="Semiconductors",
            description="GPU company",
            website="https://www.nvidia.com",
            isin="US67066G1040",
            lei=None,
            cik=None,
            market_capitalization=1.0,
            shares_outstanding=1.0,
            updated_at=None,
            raw_json_path="raw.json",
        )
    ]
    registry = service.build_company_registry(companies[:1], fundamentals)
    assert registry[0].entity_id == "company:NVDA"
    assert registry[0].sector == "Technology"
    assert registry[0].segment_primary == "ai_accelerators"
