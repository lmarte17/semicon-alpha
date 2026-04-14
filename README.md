# Semicon Alpha

This repository now contains the Phase 1 intelligence engine plus the first five terminal waves for a semiconductor event propagation product: Wave 1 analyst workflows, Wave 2 operational monitoring, Wave 3 historical research/reporting, Wave 4 scenario/thesis workflows, and Wave 5 ontology/infrastructure expansion.

The current build implements the Phase 1 ingestion, Event Intelligence, Graph / Influence Modeling, Exposure Scoring, Lag Modeling, and Market Evaluation layers described in [zervehack_semiconductor_project_plan.md](./zervehack_semiconductor_project_plan.md), with decisions shaped by the longer-term analyst terminal in [PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md](./PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md).

## What Exists

- Lithos snapshot ingestion for semiconductor news discovery
- Source-article enrichment with metadata and body extraction
- Event Intelligence conversion from enriched articles into structured semiconductor event records
- Graph construction from company, theme, ontology, and derived segment nodes/edges
- Event anchoring and deterministic first-/second-/third-order graph propagation outputs
- Lag prediction for event-company candidates using graph depth, metadata, and optional historical feedback
- Ranked event impact scoring with structural, segment, lag, historical, and obviousness components
- Market-reaction evaluation with benchmark-adjusted returns, realized lag windows, and summary KPIs
- FastAPI-backed Wave 1 product API for dashboard, event, entity, graph, search, and copilot workflows
- Browser-based intelligence terminal shell over the current world model and evidence datasets
- Local app-state persistence for watchlists, boards, saved queries, notes, alerts, and generated reports
- Wave 2 operational monitoring workflows for watchlists, explainable alerts, and saved boards
- Wave 3 historical research workflows for analog retrieval, event backtest views, and structured brief generation
- Wave 4 forward-looking workflows for scenarios, explicit assumptions, thesis monitoring, and contradiction/support tracking
- Wave 5 ontology expansion for countries, regulators, technologies, facilities, capabilities, and materials
- Graph-history snapshots and relationship-change tracking
- Hybrid retrieval index for richer terminal search over entities, events, documents, and themes
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

13. Build the hybrid retrieval index for terminal search:

```bash
semicon-alpha retrieval-sync
```

14. Refresh DuckDB views for the processed datasets:

```bash
semicon-alpha db-sync
```

15. Run the Wave 5 intelligence terminal locally:

```bash
semicon-alpha serve --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000/terminal`.

## Phase 2 Terminal Surface

The current terminal build spans the first five delivery waves on top of the Phase 1 engine.

Wave 1 provides:

- dashboard overview for recent events and non-obvious impacts
- event workspaces with ranked impacts, propagation paths, themes, and evidence
- entity workspaces with neighbors, linked events, and effect pathways
- graph path tracing between nodes
- lexical search across entities, events, themes, and documents
- hybrid retrieval index support for richer ontology-aware search
- grounded copilot responses scoped to events or entities

Wave 2 adds:

- watchlists for entities, themes, event types, and segments
- explainable alert generation over watched items and contradiction notes
- saved boards for thematic monitoring
- saved queries and contextual notes / annotations

Wave 3 adds:

- richer event analog retrieval
- event backtest workspaces showing predicted versus realized outcomes
- generated report payloads and markdown export files in `outputs/reports/`

Wave 4 adds:

- scenario workspaces with explicit assumptions and retained run history
- deterministic scenario runs over the current graph / score world model
- thesis objects with linked entities, events, or scenarios
- thesis confidence updates and monitored support / contradiction signals
- scenario and thesis alerting in the shared alert feed
- `scenario_memo` and `thesis_change_report` generation in the shared report flow

Wave 5 adds:

- explicit ontology nodes for countries, regulators, technologies, facilities, capabilities, and materials
- graph-history snapshots and change-log tracking for nodes and edges
- generic ontology workspaces through the entity surface
- ontology directory browsing in the terminal shell
- hybrid index-backed search over entities, events, documents, and themes

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
- `data/processed/graph_node_history.parquet`
- `data/processed/graph_edge_history.parquet`
- `data/processed/graph_change_log.parquet`
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
- `data/processed/ontology_nodes.parquet`
- `data/processed/ontology_relationships.parquet`
- `data/processed/retrieval_index.parquet`
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
- Wave 5 ontology expansion is still curated/config-driven rather than sourced from an external knowledge graph.
- Graph history is snapshot-based and append-only; it is designed for inspection and product timelines, not high-frequency streaming updates.
- Hybrid retrieval uses a deterministic local hashed-vector index plus lexical signals; it is intentionally lightweight and local-first.
- Lag modeling starts with deterministic heuristics plus optional empirical feedback from earlier evaluated events; it is not a learned time-series model yet.
- Exposure scoring is explainable and additive by design, with explicit structural, segment, historical, lag, and obviousness components.
- Market evaluation currently uses trading-day windows versus a semiconductor benchmark ETF to compute realized returns, abnormal returns, lag buckets, and hit-rate KPIs.
- Terminal app state is currently local-first via `data/app_state.sqlite`.
- Generated reports are stored both in app state and as markdown exports in `outputs/reports/`.
- Wave 4 scenarios are explicit and deterministic; they are not free-form speculative chat sessions.
- Thesis monitoring is evidence-driven but still single-user and local-first.
- Prompt/tool/workflow observability is still basic and local; full operational telemetry is not implemented yet.
- Collaborative multi-user workflow is still not implemented.
- The `exchange_symbols` dataset is derived from the curated instrument universe plus cached profile metadata, so it does not consume additional API quota.
- Profile syncs are cache-aware so normal daily workflows stay well under free-tier request caps.
- DuckDB is the local analytical query layer on top of parquet, not a replacement for the raw or processed storage layers.
- Relationship edges are intentionally config-driven so the graph layer remains explainable.
- If the FMP profile endpoint is unavailable, the reference sync will fall back to the most recent cached profile or the curated registry and continue.
