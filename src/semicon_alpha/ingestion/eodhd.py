from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Iterable

import httpx
from dateutil import parser as date_parser

from semicon_alpha.models.records import (
    BenchmarkConfig,
    CompanyFundamentalRecord,
    ExchangeSymbolRecord,
    MarketPriceRecord,
    UniverseCompanyConfig,
)
from semicon_alpha.settings import Settings
from semicon_alpha.utils.http import build_http_client
from semicon_alpha.utils.io import load_yaml, now_utc, stable_id, upsert_parquet, write_json


LOGGER = logging.getLogger(__name__)


class EODHDRequestError(RuntimeError):
    """Raised when EODHD responds with an error."""


class EODHDClient:
    def __init__(self, settings: Settings, client=None) -> None:
        self.settings = settings
        self.client = client or build_http_client(settings)

    def fetch_eod_prices(self, symbol: str, start: str, end: str | None = None) -> list[dict]:
        params = {"from": start, "period": "d", "fmt": "json"}
        if end:
            params["to"] = end
        return self._request_json(f"/eod/{symbol}", params=params)

    def fetch_fundamentals(self, symbol: str) -> dict:
        return self._request_json(f"/fundamentals/{symbol}", params={"fmt": "json"})

    def fetch_exchange_symbols(self, exchange_code: str) -> list[dict]:
        return self._request_json(
            f"/exchange-symbol-list/{exchange_code}",
            params={"fmt": "json"},
        )

    def _request_json(self, path: str, params: dict[str, object] | None = None) -> object:
        params = dict(params or {})
        params["api_token"] = self.settings.require_eodhd_api_key()
        try:
            response = self.client.get(f"{self.settings.eodhd_base_url}{path}", params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise EODHDRequestError(
                f"EODHD request failed for path {path} with status {status_code}"
            ) from None
        return response.json()


class EODHDIngestionService:
    def __init__(self, settings: Settings, client: EODHDClient | None = None) -> None:
        self.settings = settings
        self.client = client or EODHDClient(settings)
        self.market_price_path = settings.processed_dir / "market_prices_daily.parquet"
        self.benchmark_price_path = settings.processed_dir / "benchmark_prices_daily.parquet"
        self.fundamentals_path = settings.processed_dir / "company_fundamentals.parquet"
        self.exchange_symbols_path = settings.processed_dir / "exchange_symbols.parquet"

    def load_universe(self) -> list[UniverseCompanyConfig]:
        payload = load_yaml(self.settings.configs_dir / "universe.yaml")
        return [UniverseCompanyConfig(**item) for item in payload["companies"]]

    def load_benchmarks(self) -> list[BenchmarkConfig]:
        payload = load_yaml(self.settings.configs_dir / "benchmarks.yaml")
        return [BenchmarkConfig(**item) for item in payload["benchmarks"]]

    def sync_market_data(self, start: str, end: str | None = None) -> dict[str, int]:
        company_records = self._sync_price_set(
            instruments=self.load_universe(),
            source_table="company_prices",
            start=start,
            end=end,
            output_path=self.market_price_path,
            entity_prefix="company",
        )
        benchmark_records = self._sync_price_set(
            instruments=self.load_benchmarks(),
            source_table="benchmark_prices",
            start=start,
            end=end,
            output_path=self.benchmark_price_path,
            entity_prefix="benchmark",
        )
        return {"company_rows": company_records, "benchmark_rows": benchmark_records}

    def sync_company_fundamentals(
        self, companies: list[UniverseCompanyConfig] | None = None
    ) -> list[CompanyFundamentalRecord]:
        companies = companies or self.load_universe()
        records: list[CompanyFundamentalRecord] = []
        for company in companies:
            fetched_at = now_utc()
            try:
                payload = self.client.fetch_fundamentals(company.eodhd_symbol)
            except EODHDRequestError as exc:
                LOGGER.warning("Skipping fundamentals for %s: %s", company.ticker, exc)
                time.sleep(self.settings.request_pause_seconds)
                continue
            raw_path = self._raw_json_path("fundamentals", company.eodhd_symbol, fetched_at)
            write_json(raw_path, payload)
            general = payload.get("General", {})
            highlights = payload.get("Highlights", {})
            shares = payload.get("SharesStats", {})
            records.append(
                CompanyFundamentalRecord(
                    entity_id=f"company:{company.ticker}",
                    ticker=company.ticker,
                    eodhd_symbol=company.eodhd_symbol,
                    fetched_at_utc=fetched_at,
                    company_name=general.get("Name"),
                    exchange=general.get("Exchange"),
                    country=general.get("CountryName"),
                    sector=general.get("Sector"),
                    industry=general.get("Industry"),
                    description=general.get("Description"),
                    website=general.get("WebURL"),
                    isin=general.get("ISIN"),
                    lei=general.get("LEI"),
                    cik=general.get("CIK"),
                    market_capitalization=highlights.get("MarketCapitalization"),
                    shares_outstanding=shares.get("SharesOutstanding"),
                    updated_at=general.get("UpdatedAt"),
                    raw_json_path=str(raw_path),
                )
            )
            time.sleep(self.settings.request_pause_seconds)
        upsert_parquet(
            self.fundamentals_path,
            records,
            unique_keys=["ticker"],
            sort_by=["fetched_at_utc"],
        )
        return records

    def sync_exchange_symbols(self, exchange_codes: Iterable[str]) -> list[ExchangeSymbolRecord]:
        records: list[ExchangeSymbolRecord] = []
        for exchange_code in sorted(set(exchange_codes)):
            fetched_at = now_utc()
            try:
                payload = self.client.fetch_exchange_symbols(exchange_code)
            except EODHDRequestError as exc:
                LOGGER.warning("Skipping exchange-symbol sync for %s: %s", exchange_code, exc)
                time.sleep(self.settings.request_pause_seconds)
                continue
            raw_path = self._raw_json_path("exchange_symbols", exchange_code, fetched_at)
            write_json(raw_path, payload)
            for row in payload:
                records.append(
                    ExchangeSymbolRecord(
                        exchange_code=exchange_code,
                        code=row.get("Code"),
                        name=row.get("Name"),
                        country=row.get("Country"),
                        currency=row.get("Currency"),
                        type=row.get("Type"),
                        isin=row.get("Isin"),
                        previous_close=row.get("previousClose"),
                        exchange=row.get("Exchange"),
                        fetched_at_utc=fetched_at,
                    )
                )
            time.sleep(self.settings.request_pause_seconds)
        upsert_parquet(
            self.exchange_symbols_path,
            records,
            unique_keys=["exchange_code", "code"],
            sort_by=["fetched_at_utc"],
        )
        return records

    def _sync_price_set(
        self,
        instruments: Iterable[UniverseCompanyConfig | BenchmarkConfig],
        source_table: str,
        start: str,
        end: str | None,
        output_path: Path,
        entity_prefix: str,
    ) -> int:
        fetched_at = now_utc()
        records: list[MarketPriceRecord] = []
        for instrument in instruments:
            payload = self.client.fetch_eod_prices(instrument.eodhd_symbol, start=start, end=end)
            raw_path = self._raw_json_path("prices", instrument.eodhd_symbol, fetched_at, suffix=".json")
            write_json(raw_path, payload)
            for row in payload:
                records.append(
                    MarketPriceRecord(
                        entity_id=f"{entity_prefix}:{instrument.ticker}",
                        ticker=instrument.ticker,
                        eodhd_symbol=instrument.eodhd_symbol,
                        source_table=source_table,
                        trade_date=date_parser.parse(row["date"]).date(),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        adjusted_close=_optional_float(row.get("adjusted_close")),
                        volume=_optional_float(row.get("volume")),
                        fetched_at_utc=fetched_at,
                    )
                )
            time.sleep(self.settings.request_pause_seconds)
        upsert_parquet(
            output_path,
            records,
            unique_keys=["entity_id", "trade_date"],
            sort_by=["trade_date", "fetched_at_utc"],
        )
        return len(records)

    def _raw_json_path(
        self,
        category: str,
        name: str,
        fetched_at,
        suffix: str = ".json",
    ) -> Path:
        safe_name = name.replace("/", "_").replace(".", "_")
        return (
            self.settings.raw_dir
            / "eodhd"
            / category
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / f"{safe_name}_{fetched_at.strftime('%H%M%S')}{suffix}"
        )


def _optional_float(value) -> float | None:
    if value is None:
        return None
    return float(value)
