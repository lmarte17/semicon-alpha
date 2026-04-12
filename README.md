# Semicon Alpha

This repository is the Phase 1 intelligence-engine foundation for the ZerveHack semiconductor project.

The current build implements the full data-ingestion layer described in [zervehack_semiconductor_project_plan.md](./zervehack_semiconductor_project_plan.md), with decisions shaped by the longer-term analyst terminal in [PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md](./PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md).

## What Exists

- Lithos snapshot ingestion for semiconductor news discovery
- Source-article enrichment with metadata and body extraction
- EODHD market-price and fundamentals ingestion
- Curated ecosystem reference-data loaders for companies, themes, and relationships
- Provenance-first raw artifact storage and normalized parquet datasets
- CLI entrypoints and tests

## Why It Is Shaped This Way

Phase 2 requires stable entities, evidence links, document history, and inspectable intermediate datasets. The ingestion layer therefore stores:

- immutable raw snapshots and source HTML
- normalized discovery/enrichment tables
- stable IDs for articles, companies, themes, and relationships
- reference tables that can feed the future graph and terminal layers

## Quick Start

1. Ensure `EODHD_API_KEY` is available in the environment or `.env`.
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

5. Build reference datasets and fetch company fundamentals:

```bash
semicon-alpha reference-sync
```

6. Backfill prices for the curated universe and benchmarks:

```bash
semicon-alpha market-sync --start 2024-01-01
```

## Primary Datasets

- `data/processed/lithos_snapshots.parquet`
- `data/processed/news_source_registry.parquet`
- `data/processed/news_article_observations.parquet`
- `data/processed/news_articles_discovered.parquet`
- `data/processed/news_articles_enriched.parquet`
- `data/processed/company_registry.parquet`
- `data/processed/company_relationships.parquet`
- `data/processed/theme_nodes.parquet`
- `data/processed/theme_relationships.parquet`
- `data/processed/market_prices_daily.parquet`
- `data/processed/benchmark_prices_daily.parquet`
- `data/processed/company_fundamentals.parquet`

## Notes

- Lithos is treated as a discovery surface, not the final source of truth for `published_at`.
- EODHD is used for price history and company fundamentals.
- Relationship edges are intentionally config-driven so the graph layer remains explainable.
