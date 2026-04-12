from semicon_alpha.ingestion.eodhd import EODHDClient, EODHDIngestionService, EODHDRequestError
from semicon_alpha.settings import Settings


class FailingFundamentalsClient:
    def fetch_fundamentals(self, symbol):
        raise EODHDRequestError("EODHD request failed for path /fundamentals/TEST.US with status 403")


def test_sync_company_fundamentals_skips_provider_errors():
    settings = Settings(EODHD_API_KEY="test-token")
    service = EODHDIngestionService(settings, client=FailingFundamentalsClient())
    companies = service.load_universe()[:1]
    records = service.sync_company_fundamentals(companies)
    assert records == []
