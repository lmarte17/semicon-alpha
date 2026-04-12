from semicon_alpha.ingestion.eodhd import EODHDClient
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
        if "/eod/" in url:
            return FakeResponse([{"date": "2026-04-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "adjusted_close": 1.4, "volume": 10}])
        if "/fundamentals/" in url:
            return FakeResponse({"General": {"Name": "NVIDIA Corporation"}})
        if "/exchange-symbol-list/" in url:
            return FakeResponse([{"Code": "NVDA", "Name": "NVIDIA Corporation"}])
        raise AssertionError(f"Unexpected URL: {url}")


def test_eodhd_client_uses_expected_paths():
    settings = Settings(EODHD_API_KEY="test-token")
    client = EODHDClient(settings=settings, client=FakeClient())
    prices = client.fetch_eod_prices("NVDA.US", start="2026-04-01", end="2026-04-02")
    fundamentals = client.fetch_fundamentals("NVDA.US")
    symbols = client.fetch_exchange_symbols("US")

    assert prices[0]["close"] == 1.5
    assert fundamentals["General"]["Name"] == "NVIDIA Corporation"
    assert symbols[0]["Code"] == "NVDA"
