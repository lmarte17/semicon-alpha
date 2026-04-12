# Semicon Alpha

This repository is the Phase 1 intelligence-engine foundation for a semiconductor event propagation product.

The current build implements the Phase 1 ingestion and Event Intelligence layers described in [zervehack_semiconductor_project_plan.md](./zervehack_semiconductor_project_plan.md), with decisions shaped by the longer-term analyst terminal in [PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md](./PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md).

## What Exists

- Lithos snapshot ingestion for semiconductor news discovery
- Source-article enrichment with metadata and body extraction
- Event Intelligence conversion from enriched articles into structured semiconductor event records
- FMP market-price and company-profile ingestion
- Curated instrument-directory generation for exchange/ticker reference data
- Curated ecosystem reference-data loaders for companies, themes, and relationships
- Provenance-first raw artifact storage and normalized parquet datasets
- DuckDB query layer over the processed parquet datasets
- CLI entrypoints and tests

## Why It Is Shaped This Way

Phase 2 requires stable entities, evidence links, document history, and inspectable intermediate datasets. The current Phase 1 build therefore stores:

- immutable raw snapshots and source HTML
- normalized discovery, enrichment, and event-intelligence tables
- stable IDs for articles, companies, themes, and relationships
- reference tables that can feed the future graph and terminal layers

## Quick Start

1. Ensure `FMP_API_KEY` is available in the environment or `.env`.
2. Install the package:

```bash
pip install -e ".[dev]"
```

3. Capture a Lithos snapshot and parse discovered articles:

```bash
semicon-alpha news-snapshot
```

4. Enrich the most recent discovered articles from their source pages:

```bash
semicon-alpha news-enrich --limit 20
```

5. Convert enriched articles into structured event datasets:

```bash
semicon-alpha event-sync --limit 20
```

6. Build reference datasets and fetch company profiles:

```bash
semicon-alpha reference-sync
```

7. Backfill prices for the curated universe and benchmarks:

```bash
semicon-alpha market-sync --start 2024-01-01
```

8. Refresh DuckDB views for the processed datasets:

```bash
semicon-alpha db-sync
```

## Primary Datasets

- `data/processed/lithos_snapshots.parquet`
- `data/processed/news_source_registry.parquet`
- `data/processed/news_article_observations.parquet`
- `data/processed/news_articles_discovered.parquet`
- `data/processed/news_articles_enriched.parquet`
- `data/processed/news_event_entities.parquet`
- `data/processed/news_event_classifications.parquet`
- `data/processed/news_event_themes.parquet`
- `data/processed/news_events_structured.parquet`
- `data/processed/company_registry.parquet`
- `data/processed/company_relationships.parquet`
- `data/processed/theme_nodes.parquet`
- `data/processed/theme_relationships.parquet`
- `data/processed/market_prices_daily.parquet`
- `data/processed/benchmark_prices_daily.parquet`
- `data/processed/exchange_symbols.parquet`
- `data/processed/company_fundamentals.parquet`
- `data/semicon_alpha.duckdb`

## Notes

- Lithos is treated as a discovery surface, not the final source of truth for `published_at`.
- FMP is used for price history and company profiles.
- Event Intelligence is deterministic and config-driven for the current MVP, with tracked-universe entity extraction and taxonomy-based event classification.
- The `exchange_symbols` dataset is derived from the curated instrument universe plus cached profile metadata, so it does not consume additional API quota.
- Profile syncs are cache-aware so normal daily workflows stay well under free-tier request caps.
- DuckDB is the local analytical query layer on top of parquet, not a replacement for the raw or processed storage layers.
- Relationship edges are intentionally config-driven so the graph layer remains explainable.
- If the FMP profile endpoint is unavailable, the reference sync will fall back to the most recent cached profile or the curated registry and continue.
