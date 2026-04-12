from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import httpx
import pandas as pd
from dateutil import parser as date_parser

from semicon_alpha.models.records import (
    BenchmarkConfig,
    CompanyFundamentalRecord,
    ExchangeSymbolRecord,
    MarketPriceRecord,
    UniverseCompanyConfig,
)
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.http import build_http_client
from semicon_alpha.utils.io import load_yaml, now_utc, upsert_parquet, write_json


LOGGER = logging.getLogger(__name__)


class FMPRequestError(RuntimeError):
    """Raised when FMP responds with an error."""


class FMPClient:
    def __init__(self, settings: Settings, client=None) -> None:
        self.settings = settings
        self.client = client or build_http_client(settings)

    def fetch_eod_prices(self, symbol: str, start: str, end: str | None = None) -> list[dict]:
        params: dict[str, object] = {"symbol": normalize_provider_symbol(symbol), "from": start}
        if end:
            params["to"] = end
        payload = self._request_json("/historical-price-eod/full", params=params)
        return _extract_collection(payload)

    def fetch_company_profile(self, symbol: str) -> dict:
        payload = self._request_json(
            "/profile",
            params={"symbol": normalize_provider_symbol(symbol)},
        )
        rows = _extract_collection(payload)
        return rows[0] if rows else {}

    def _request_json(self, path: str, params: dict[str, object] | None = None) -> object:
        params = dict(params or {})
        params["apikey"] = self.settings.require_fmp_api_key()
        try:
            response = self.client.get(f"{self.settings.fmp_base_url}{path}", params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise FMPRequestError(
                f"FMP request failed for path {path} with status {status_code}"
            ) from None
        return response.json()


class FMPIngestionService:
    def __init__(
        self,
        settings: Settings,
        client: FMPClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or FMPClient(settings)
        self.catalog = DuckDBCatalog(settings)
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
        self.catalog.refresh_processed_views()
        return {"company_rows": company_records, "benchmark_rows": benchmark_records}

    def sync_company_fundamentals(
        self, companies: list[UniverseCompanyConfig] | None = None
    ) -> list[CompanyFundamentalRecord]:
        companies = companies or self.load_universe()
        cached_records = self._load_cached_fundamentals()
        cutoff = now_utc() - timedelta(days=self.settings.market_profile_refresh_days)
        records: list[CompanyFundamentalRecord] = []
        new_records: list[CompanyFundamentalRecord] = []
        skipped_for_freshness = 0

        for company in companies:
            cached_record = cached_records.get(company.ticker)
            if cached_record and cached_record.fetched_at_utc >= cutoff:
                records.append(cached_record)
                skipped_for_freshness += 1
                continue

            fetched_at = now_utc()
            try:
                payload = self.client.fetch_company_profile(company.eodhd_symbol)
            except FMPRequestError as exc:
                LOGGER.warning("Skipping company profile for %s: %s", company.ticker, exc)
                if cached_record:
                    records.append(cached_record)
                time.sleep(self.settings.request_pause_seconds)
                continue
            raw_path = self._raw_json_path("profiles", company.eodhd_symbol, fetched_at)
            write_json(raw_path, payload)
            record = _build_company_fundamental_record(
                company=company,
                payload=payload,
                fetched_at=fetched_at,
                raw_path=raw_path,
            )
            records.append(record)
            new_records.append(record)
            time.sleep(self.settings.request_pause_seconds)

        if new_records:
            upsert_parquet(
                self.fundamentals_path,
                new_records,
                unique_keys=["ticker"],
                sort_by=["fetched_at_utc"],
            )
            self.catalog.refresh_processed_views()
        LOGGER.info(
            "Company profile sync completed with %s fresh fetches and %s cache hits",
            len(new_records),
            skipped_for_freshness,
        )
        return records

    def sync_exchange_symbols(self, exchange_codes: Iterable[str]) -> list[ExchangeSymbolRecord]:
        requested_codes = {_normalize_exchange_code(code) for code in exchange_codes if code}
        fundamentals = self._load_cached_fundamentals()
        fetched_at = now_utc()
        records: list[ExchangeSymbolRecord] = []
        for company in self.load_universe():
            exchange_code = _normalize_exchange_code(company.exchange)
            if requested_codes and exchange_code not in requested_codes:
                continue
            fundamental = fundamentals.get(company.ticker)
            records.append(
                ExchangeSymbolRecord(
                    exchange_code=exchange_code,
                    code=company.ticker,
                    name=fundamental.company_name if fundamental and fundamental.company_name else company.company_name,
                    country=fundamental.country if fundamental and fundamental.country else company.country,
                    currency=None,
                    type="equity",
                    isin=fundamental.isin if fundamental else None,
                    previous_close=None,
                    exchange=fundamental.exchange if fundamental and fundamental.exchange else company.exchange,
                    fetched_at_utc=fetched_at,
                )
            )
        upsert_parquet(
            self.exchange_symbols_path,
            records,
            unique_keys=["exchange_code", "code"],
            sort_by=["fetched_at_utc"],
        )
        self.catalog.refresh_processed_views()
        time.sleep(self.settings.request_pause_seconds)
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
        requested_start = date.fromisoformat(start)
        requested_end = date.fromisoformat(end) if end else None
        today_utc = now_utc().date()
        existing_state = self._load_price_state(output_path)
        records: list[MarketPriceRecord] = []
        request_count = 0
        cache_skips = 0

        for instrument in instruments:
            entity_id = f"{entity_prefix}:{instrument.ticker}"
            windows = build_price_sync_windows(
                state=existing_state.get(entity_id),
                requested_start=requested_start,
                requested_end=requested_end,
                today=today_utc,
            )
            if not windows:
                cache_skips += 1
                continue

            for window_start, window_end in windows:
                fetched_at = now_utc()
                payload = self.client.fetch_eod_prices(
                    instrument.eodhd_symbol,
                    start=window_start.isoformat(),
                    end=window_end.isoformat() if window_end else None,
                )
                raw_path = self._raw_json_path(
                    "prices",
                    instrument.eodhd_symbol,
                    fetched_at,
                    suffix=".json",
                )
                write_json(raw_path, payload)
                request_count += 1
                for row in payload:
                    trade_date = _coerce_trade_date(row)
                    if trade_date is None:
                        continue
                    records.append(
                        MarketPriceRecord(
                            entity_id=entity_id,
                            ticker=instrument.ticker,
                            eodhd_symbol=instrument.eodhd_symbol,
                            source_table=source_table,
                            trade_date=trade_date,
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            adjusted_close=_optional_float(
                                row.get("adjusted_close") or row.get("adjClose")
                            ),
                            volume=_optional_float(row.get("volume")),
                            fetched_at_utc=fetched_at,
                        )
                    )
                time.sleep(self.settings.request_pause_seconds)

        if records:
            upsert_parquet(
                output_path,
                records,
                unique_keys=["entity_id", "trade_date"],
                sort_by=["trade_date", "fetched_at_utc"],
            )
        LOGGER.info(
            "Price sync completed with %s API requests and %s cached instruments skipped",
            request_count,
            cache_skips,
        )
        return len(records)

    def _load_cached_fundamentals(self) -> dict[str, CompanyFundamentalRecord]:
        if not self.fundamentals_path.exists():
            return {}
        frame = pd.read_parquet(self.fundamentals_path)
        if frame.empty:
            return {}
        frame = frame.sort_values("fetched_at_utc").drop_duplicates(subset=["ticker"], keep="last")
        cached: dict[str, CompanyFundamentalRecord] = {}
        for row in frame.to_dict(orient="records"):
            record = _company_fundamental_from_row(row)
            cached[record.ticker] = record
        return cached

    def _load_price_state(self, output_path: Path) -> dict[str, dict[str, object]]:
        if not output_path.exists():
            return {}
        frame = pd.read_parquet(
            output_path,
            columns=["entity_id", "trade_date", "fetched_at_utc"],
        )
        if frame.empty:
            return {}
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], utc=True).dt.date
        frame["fetched_at_utc"] = pd.to_datetime(frame["fetched_at_utc"], utc=True)
        state: dict[str, dict[str, object]] = {}
        for entity_id, entity_frame in frame.groupby("entity_id"):
            state[entity_id] = {
                "min_trade_date": entity_frame["trade_date"].min(),
                "max_trade_date": entity_frame["trade_date"].max(),
                "last_fetched_at_utc": entity_frame["fetched_at_utc"].max().to_pydatetime(),
            }
        return state

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
            / "fmp"
            / category
            / fetched_at.strftime("%Y")
            / fetched_at.strftime("%m")
            / fetched_at.strftime("%d")
            / f"{safe_name}_{fetched_at.strftime('%H%M%S')}{suffix}"
        )


def build_price_sync_windows(
    state: dict[str, object] | None,
    requested_start: date,
    requested_end: date | None,
    today: date,
) -> list[tuple[date, date | None]]:
    if state is None:
        return [(requested_start, requested_end)]

    min_trade_date = state["min_trade_date"]
    max_trade_date = state["max_trade_date"]
    last_fetched_at = state["last_fetched_at_utc"]
    windows: list[tuple[date, date | None]] = []

    if requested_start < min_trade_date:
        earlier_end = min(
            requested_end or (min_trade_date - timedelta(days=1)),
            min_trade_date - timedelta(days=1),
        )
        if requested_start <= earlier_end:
            windows.append((requested_start, earlier_end))

    if requested_end is not None:
        if requested_end <= max_trade_date and requested_start >= min_trade_date:
            return windows
        later_start = max(requested_start, max_trade_date + timedelta(days=1))
        if later_start <= requested_end:
            windows.append((later_start, requested_end))
        return windows

    if last_fetched_at.date() >= today:
        return windows

    later_start = max(requested_start, max_trade_date + timedelta(days=1))
    if later_start <= today:
        windows.append((later_start, None))
    return windows


def normalize_provider_symbol(symbol: str) -> str:
    if "." not in symbol:
        return symbol
    base, suffix = symbol.rsplit(".", 1)
    if suffix.isalpha() and suffix.isupper() and len(suffix) >= 2:
        return base
    return symbol


def _extract_collection(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("historical", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _build_company_fundamental_record(
    company: UniverseCompanyConfig,
    payload: dict,
    fetched_at: datetime,
    raw_path: Path,
) -> CompanyFundamentalRecord:
    return CompanyFundamentalRecord(
        entity_id=f"company:{company.ticker}",
        ticker=company.ticker,
        eodhd_symbol=company.eodhd_symbol,
        fetched_at_utc=fetched_at,
        company_name=_first_present(payload, "companyName", "name"),
        exchange=_first_present(payload, "exchangeShortName", "exchange"),
        country=_first_present(payload, "country"),
        sector=_first_present(payload, "sector"),
        industry=_first_present(payload, "industry"),
        description=_first_present(payload, "description"),
        website=_first_present(payload, "website"),
        isin=_first_present(payload, "isin"),
        lei=_first_present(payload, "lei"),
        cik=_string_or_none(payload.get("cik")),
        market_capitalization=_optional_float(
            payload.get("marketCap") or payload.get("mktCap")
        ),
        shares_outstanding=_optional_float(
            payload.get("sharesOutstanding") or payload.get("shares")
        ),
        updated_at=_first_present(payload, "lastUpdated", "updatedAt"),
        raw_json_path=str(raw_path),
    )


def _company_fundamental_from_row(row: dict) -> CompanyFundamentalRecord:
    return CompanyFundamentalRecord(
        entity_id=row["entity_id"],
        ticker=row["ticker"],
        eodhd_symbol=row["eodhd_symbol"],
        fetched_at_utc=_coerce_datetime(row["fetched_at_utc"]),
        company_name=_nullify_frame_value(row.get("company_name")),
        exchange=_nullify_frame_value(row.get("exchange")),
        country=_nullify_frame_value(row.get("country")),
        sector=_nullify_frame_value(row.get("sector")),
        industry=_nullify_frame_value(row.get("industry")),
        description=_nullify_frame_value(row.get("description")),
        website=_nullify_frame_value(row.get("website")),
        isin=_nullify_frame_value(row.get("isin")),
        lei=_nullify_frame_value(row.get("lei")),
        cik=_nullify_frame_value(row.get("cik")),
        market_capitalization=_optional_float(_nullify_frame_value(row.get("market_capitalization"))),
        shares_outstanding=_optional_float(_nullify_frame_value(row.get("shares_outstanding"))),
        updated_at=_nullify_frame_value(row.get("updated_at")),
        raw_json_path=row["raw_json_path"],
    )


def _normalize_exchange_code(value: str | None) -> str:
    if not value:
        return "UNKNOWN"
    return value.strip().upper()


def _coerce_trade_date(row: dict) -> date | None:
    raw_value = row.get("date")
    if not raw_value:
        return None
    return date_parser.parse(raw_value).date()


def _coerce_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    parsed = date_parser.isoparse(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _optional_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return float(value)


def _nullify_frame_value(value):
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def _first_present(payload: dict, *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        string_value = _string_or_none(value)
        if string_value:
            return string_value
    return None


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    value = str(value).strip()
    return value or None
