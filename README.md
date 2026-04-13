# Semicon Alpha

This repository now contains the Phase 1 intelligence engine plus the first Wave 1 analyst-terminal MVP for a semiconductor event propagation product.

The current build implements the Phase 1 ingestion, Event Intelligence, Graph / Influence Modeling, Exposure Scoring, Lag Modeling, and Market Evaluation layers described in [zervehack_semiconductor_project_plan.md](./zervehack_semiconductor_project_plan.md), with decisions shaped by the longer-term analyst terminal in [PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md](./PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md).

## What Exists

- Lithos snapshot ingestion for semiconductor news discovery
- Source-article enrichment with metadata and body extraction
- Event Intelligence conversion from enriched articles into structured semiconductor event records
- Graph construction from company, theme, and derived segment nodes/edges
- Event anchoring and deterministic first-/second-/third-order graph propagation outputs
- Lag prediction for event-company candidates using graph depth, metadata, and optional historical feedback
- Ranked event impact scoring with structural, segment, lag, historical, and obviousness components
- Market-reaction evaluation with benchmark-adjusted returns, realized lag windows, and summary KPIs
- FastAPI-backed Wave 1 product API for dashboard, event, entity, graph, search, and copilot workflows
- Browser-based intelligence terminal shell over the current world model and evidence datasets
- FMP market-price and company-profile ingestion
- Curated instrument-directory generation for exchange/ticker reference data
- Curated ecosystem reference-data loaders for companies, themes, and relationships
- Provenance-first raw artifact storage and normalized parquet datasets
- DuckDB query layer over the processed parquet datasets
- CLI entrypoints and tests

## Why It Is Shaped This Way

Phase 2 requires stable entities, evidence links, document history, and inspectable intermediate datasets. The current Phase 1 build therefore stores:

- immutable raw snapshots and source HTML
- normalized discovery, enrichment, event-intelligence, graph-propagation, scoring, and evaluation tables
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

7. Build unified graph datasets:

```bash
semicon-alpha graph-sync
```

8. Generate event anchors and propagated graph influence outputs:

```bash
semicon-alpha graph-propagate --limit 20
```

9. Generate lag predictions for impacted companies:

```bash
semicon-alpha lag-sync --limit 20
```

10. Rank event-company impact candidates:

```bash
semicon-alpha score-sync --limit 20
```

11. Backfill prices for the curated universe and benchmarks:

```bash
semicon-alpha market-sync --start 2024-01-01
```

12. Evaluate predictions against realized market moves:

```bash
semicon-alpha evaluate-sync --limit 20
```

13. Refresh DuckDB views for the processed datasets:

```bash
semicon-alpha db-sync
```

14. Run the Wave 1 intelligence terminal locally:

```bash
semicon-alpha serve --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/terminal`.

## Wave 1 Terminal Surface

Wave 1 is the first analyst workflow layer on top of the Phase 1 engine. It currently provides:

- dashboard overview for recent events and non-obvious impacts
- event workspaces with ranked impacts, propagation paths, themes, and evidence
- entity workspaces with neighbors, linked events, and effect pathways
- graph path tracing between nodes
- lexical search across entities, events, themes, and documents
- grounded copilot responses scoped to events or entities

Current API routes are mounted under `/api`, and the browser shell is served at `/terminal`.

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
- `data/processed/graph_nodes.parquet`
- `data/processed/graph_edges.parquet`
- `data/processed/event_graph_anchors.parquet`
- `data/processed/event_propagation_paths.parquet`
- `data/processed/event_node_influence.parquet`
- `data/processed/lag_profiles.parquet`
- `data/processed/event_lag_predictions.parquet`
- `data/processed/event_impact_scores.parquet`
- `data/processed/event_market_reactions.parquet`
- `data/processed/evaluation_summary.parquet`
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
- The graph layer is parquet-first: typed node/edge datasets are the source of truth, and propagation is deterministic and rule-driven.
- Lag modeling starts with deterministic heuristics plus optional empirical feedback from earlier evaluated events; it is not a learned time-series model yet.
- Exposure scoring is explainable and additive by design, with explicit structural, segment, historical, lag, and obviousness components.
- Market evaluation currently uses trading-day windows versus a semiconductor benchmark ETF to compute realized returns, abnormal returns, lag buckets, and hit-rate KPIs.
- Wave 1 is intentionally read-heavy and evidence-first; it is not yet the full Phase 2 system for watchlists, alerts, boards, scenarios, or collaborative workflows.
- The `exchange_symbols` dataset is derived from the curated instrument universe plus cached profile metadata, so it does not consume additional API quota.
- Profile syncs are cache-aware so normal daily workflows stay well under free-tier request caps.
- DuckDB is the local analytical query layer on top of parquet, not a replacement for the raw or processed storage layers.
- Relationship edges are intentionally config-driven so the graph layer remains explainable.
- If the FMP profile endpoint is unavailable, the reference sync will fall back to the most recent cached profile or the curated registry and continue.
