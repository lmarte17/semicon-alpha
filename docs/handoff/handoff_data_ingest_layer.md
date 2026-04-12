# Data Ingestion Layer Handoff

## Purpose

This document captures the current end-state of the Phase 1 data-ingestion layer so a new session can pick up cleanly and move into the Event Intelligence layer without having to rediscover architecture, storage, or provider decisions.

This work implements the ingestion portion of the product described in [zervehack_semiconductor_project_plan.md](../../zervehack_semiconductor_project_plan.md), specifically the modular Phase 1 foundation for:

- news and event discovery
- market data ingestion
- ecosystem reference data
- durable intermediate datasets that can feed event extraction, graph propagation, and later backtesting

## What Exists

The repo now contains a working Phase 1 ingestion system with these major components:

1. Lithos news discovery
   - Fetches the Lithos semiconductor page
   - Stores the raw HTML snapshot
   - Parses:
     - source registry
     - article observations
     - deduplicated discovered articles

2. Source article enrichment
   - Fetches original article URLs from discovered articles
   - Extracts canonical URL, published timestamp, title, site, author, description, excerpt, and body text where possible
   - Stores raw source documents before normalization

3. Market data ingestion
   - Uses FMP for daily historical OHLCV price history
   - Supports the curated semiconductor universe plus benchmark ETFs
   - Preserves the existing `eodhd_symbol` field in configs/schemas for compatibility, but translates symbols at the API boundary for FMP

4. Reference data ingestion
   - Loads curated company universe, benchmarks, themes, and relationship edges from config
   - Fetches FMP company profiles
   - Builds `company_registry`
   - Builds `exchange_symbols` from the curated universe plus cached profile metadata
   - Writes separate company and theme relationship tables

5. DuckDB query layer
   - Creates a local DuckDB database over all processed parquet datasets
   - Registers one view per processed parquet file
   - Maintains a `dataset_catalog` table with dataset path and row counts

## Storage Model

The storage decision is now:

- raw artifacts are stored on disk under `data/raw/`
- normalized analytical datasets are stored as parquet under `data/processed/`
- DuckDB at `data/semicon_alpha.duckdb` is the query layer on top of parquet

This matches the product plan well:

- raw artifacts preserve provenance
- parquet stays simple, inspectable, and easy to backfill
- DuckDB gives fast local joins and SQL for the next layers

This is intentionally not a hosted database design yet. The current design is optimized for:

- local product iteration
- deterministic pipelines
- inspectable intermediate state
- future event intelligence and backtesting

## Current Source Decisions

### News / event discovery

- Provider: Lithos
- Role: discovery surface, not source of truth for exact publish time
- Exact publish timestamps are recovered from original article pages during enrichment

### Market data

- Provider: FMP
- Scope used:
  - historical daily prices
  - company profiles

### Exchange / symbol directory

- Not using a broad paid or brittle external directory feed
- `exchange_symbols` is generated from the curated tracked universe plus cached profile metadata
- This keeps the dataset useful without spending extra request budget

## Request Budget Controls

The ingestion layer is now designed to be conservative with FMP usage.

Implemented controls:

- company profiles are cached and only refreshed after `market_profile_refresh_days` (currently 7)
- price sync inspects existing parquet state and avoids same-day re-fetches
- incremental sync logic only requests missing windows outside already stored ranges
- `exchange_symbols` does not trigger additional provider requests

Implication:

- the first full historical backfill is still the expensive run
- routine daily reruns are much cheaper

## Core Output Datasets

The ingestion layer now produces these primary parquet datasets:

- `lithos_snapshots.parquet`
- `news_source_registry.parquet`
- `news_article_observations.parquet`
- `news_articles_discovered.parquet`
- `news_articles_enriched.parquet`
- `company_registry.parquet`
- `company_fundamentals.parquet`
- `company_relationships.parquet`
- `theme_nodes.parquet`
- `theme_relationships.parquet`
- `market_prices_daily.parquet`
- `benchmark_prices_daily.parquet`
- `exchange_symbols.parquet`

DuckDB also exposes these through views in:

- `data/semicon_alpha.duckdb`

## CLI Commands

The current CLI supports:

- `semicon-alpha news-snapshot`
- `semicon-alpha news-enrich --limit 25`
- `semicon-alpha reference-sync`
- `semicon-alpha market-sync --start YYYY-MM-DD`
- `semicon-alpha ingest-all --start YYYY-MM-DD --enrich-limit 25`
- `semicon-alpha db-sync`

## Alignment With The Product Plan

Relative to the ingestion requirements in the project plan, the current implementation satisfies the following core needs:

1. News / event data foundation
   - We have semiconductor-relevant article discovery
   - We have source metadata and article body extraction
   - We have raw source preservation

2. Market data foundation
   - We have daily OHLCV for the curated semiconductor universe
   - We have benchmark ETF price history

3. Ecosystem reference foundation
   - We have company metadata
   - We have segment classification
   - We have market-cap buckets
   - We have manually curated relationship edges and themes

4. Modular pipeline requirement
   - News, enrichment, market, reference, and query-layer concerns are separated into distinct services

5. Deterministic / inspectable pipeline requirement
   - Raw artifacts are persisted
   - Processed outputs are normalized into explicit parquet tables
   - DuckDB gives a stable analytical interface for validation and downstream work

This means the repo is now in a good position to start the Event Intelligence layer described in the plan.

## Important Implementation Details

- The config schema still uses `eodhd_symbol` as the instrument field name.
  - This was kept intentionally to avoid churn across configs and models.
  - FMP symbol normalization happens inside the FMP client.

- The reference layer is curated by design.
  - `company_registry`, `theme_nodes`, and relationship edges are intended to stay explicit and explainable.

- DuckDB is not the canonical storage layer.
  - parquet remains the durable analytical system of record
  - DuckDB is the local query interface

## Verification Status

Verified locally:

- full test suite passes
- live FMP price-history request succeeds
- live FMP company-profile request succeeds
- DuckDB catalog rebuild succeeds

The system is stable enough to move into the next layer.

## Recommended Next Step

Begin the Event Intelligence layer.

The next session should focus on converting `news_articles_enriched` into structured semiconductor event objects with explicit intermediate stages, likely starting with:

1. company/entity extraction
2. event taxonomy classification
3. segment/theme mapping
4. direction and severity estimation
5. explanation/provenance fields

The ingestion layer is already shaped to support that work.
