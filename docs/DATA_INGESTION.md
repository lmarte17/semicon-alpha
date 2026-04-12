# Data Ingestion Layer

This repository implements the Phase 1 ingestion layer for the semiconductor event propagation engine.

The storage layout is deliberately split into:

- raw artifacts under `data/raw/`
- normalized parquet datasets under `data/processed/`
- a DuckDB catalog at `data/semicon_alpha.duckdb` for local SQL and downstream analytics

## Design Rules

1. Raw source artifacts are stored before normalization.
2. All normalized records receive stable IDs.
3. Discovery and enrichment are separated.
4. Curated reference knowledge remains explicit and editable.
5. Dataset shapes favor future graph, event, and analyst-terminal queries.

## News Flow

`Lithos snapshot -> article observations -> deduped discovered articles -> source enrichment`

### Raw Artifacts

- `data/raw/lithos_snapshots/...`
- `data/raw/source_articles/...`

### Processed Tables

- `lithos_snapshots.parquet`
- `news_source_registry.parquet`
- `news_article_observations.parquet`
- `news_articles_discovered.parquet`
- `news_articles_enriched.parquet`

Lithos is used as the discovery layer. Exact publish timestamps are recovered from the original source pages whenever possible.

## Market Data Flow

`curated universe + benchmarks -> FMP price history -> normalized daily price tables`

### Processed Tables

- `market_prices_daily.parquet`
- `benchmark_prices_daily.parquet`

## Reference Data Flow

`curated configs + FMP company profiles -> company registry, themes, relationship edges, and instrument directory`

### Processed Tables

- `company_registry.parquet`
- `company_fundamentals.parquet`
- `theme_nodes.parquet`
- `company_relationships.parquet`
- `theme_relationships.parquet`
- `exchange_symbols.parquet`

## Query Layer

DuckDB is kept as a local query engine on top of parquet rather than the system of record.

- `data/semicon_alpha.duckdb`
- one DuckDB view per processed parquet dataset
- `dataset_catalog` table with dataset paths and row counts

This keeps Phase 1 aligned with the product plan:

- raw artifacts stay immutable
- parquet stays easy to inspect and backfill
- DuckDB gives us fast joins and analytical queries for the event and backtest layers

## CLI Entry Points

```bash
semicon-alpha news-snapshot
semicon-alpha news-enrich --limit 25
semicon-alpha reference-sync
semicon-alpha market-sync --start 2024-01-01
semicon-alpha ingest-all --start 2024-01-01 --enrich-limit 25
semicon-alpha db-sync
```
