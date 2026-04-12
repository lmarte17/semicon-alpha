from __future__ import annotations

import argparse
import logging

from semicon_alpha.ingestion.fmp import FMPIngestionService
from semicon_alpha.ingestion.lithos import LithosIngestionService
from semicon_alpha.ingestion.reference import ReferenceDataService
from semicon_alpha.ingestion.source_enrichment import SourceEnrichmentService
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.logging import configure_logging


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Semicon Alpha ingestion CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("news-snapshot", help="Fetch and parse the Lithos semicon page")

    news_enrich = subparsers.add_parser(
        "news-enrich", help="Fetch and enrich discovered source articles"
    )
    news_enrich.add_argument("--limit", type=int, default=25)
    news_enrich.add_argument("--force", action="store_true")

    market_sync = subparsers.add_parser(
        "market-sync", help="Fetch FMP daily price history for the curated universe"
    )
    market_sync.add_argument("--start", required=True, help="Start date in YYYY-MM-DD format")
    market_sync.add_argument("--end", help="Optional end date in YYYY-MM-DD format")

    reference_sync = subparsers.add_parser(
        "reference-sync", help="Build reference datasets and fetch company profiles"
    )
    reference_sync.add_argument("--skip-exchange-symbols", action="store_true")

    ingest_all = subparsers.add_parser(
        "ingest-all", help="Run news, reference, and market ingestion together"
    )
    ingest_all.add_argument("--start", required=True, help="Start date in YYYY-MM-DD format")
    ingest_all.add_argument("--end", help="Optional end date in YYYY-MM-DD format")
    ingest_all.add_argument("--enrich-limit", type=int, default=25)
    ingest_all.add_argument("--skip-exchange-symbols", action="store_true")

    subparsers.add_parser("db-sync", help="Refresh DuckDB views over processed parquet datasets")

    return parser


def main() -> None:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings()
    settings.ensure_directories()

    lithos_service = LithosIngestionService(settings)
    enrichment_service = SourceEnrichmentService(settings)
    market_service = FMPIngestionService(settings)
    reference_service = ReferenceDataService(settings, market_service)
    catalog = DuckDBCatalog(settings)

    if args.command == "news-snapshot":
        result = lithos_service.run()
        LOGGER.info("Captured Lithos snapshot %s with %s articles", result["snapshot_id"], result["article_count"])
        return

    if args.command == "news-enrich":
        result = enrichment_service.run(limit=args.limit, force=args.force)
        LOGGER.info("Enriched %s articles", result["processed_count"])
        return

    if args.command == "market-sync":
        result = market_service.sync_market_data(start=args.start, end=args.end)
        LOGGER.info("Fetched %s company rows and %s benchmark rows", result["company_rows"], result["benchmark_rows"])
        return

    if args.command == "reference-sync":
        result = reference_service.sync_reference_data(skip_exchange_symbols=args.skip_exchange_symbols)
        LOGGER.info(
            "Reference sync complete with %s companies, %s themes, %s relationships, %s fundamentals",
            result["company_count"],
            result["theme_count"],
            result["relationship_count"],
            result["fundamental_count"],
        )
        return

    if args.command == "ingest-all":
        snapshot = lithos_service.run()
        enriched = enrichment_service.run(limit=args.enrich_limit, force=False)
        reference = reference_service.sync_reference_data(
            skip_exchange_symbols=args.skip_exchange_symbols
        )
        market = market_service.sync_market_data(start=args.start, end=args.end)
        LOGGER.info(
            "All ingestion complete: snapshot=%s articles=%s enriched=%s company_rows=%s benchmark_rows=%s companies=%s",
            snapshot["snapshot_id"],
            snapshot["article_count"],
            enriched["processed_count"],
            market["company_rows"],
            market["benchmark_rows"],
            reference["company_count"],
        )
        return

    if args.command == "db-sync":
        result = catalog.refresh_processed_views()
        LOGGER.info("DuckDB catalog refreshed for %s datasets", result["dataset_count"])
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
