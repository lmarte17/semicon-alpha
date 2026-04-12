# Event Intelligence Layer

This repository now includes the Phase 1 Event Intelligence layer on top of the existing ingestion foundation.

## Purpose

The layer converts `news_articles_enriched.parquet` into structured semiconductor event records with explicit intermediate stages that can be inspected in parquet or DuckDB.

The pipeline is intentionally deterministic and modular:

1. tracked-company extraction
2. taxonomy scoring across candidate event types
3. theme mapping from taxonomy, direct theme signals, and curated company-theme edges
4. segment, direction, severity, confidence, and market-relevance derivation
5. structured event summary and reasoning output

## Inputs

Primary input:

- `news_articles_enriched.parquet`

Optional/fallback input:

- `news_articles_discovered.parquet` for headline/source fallback

Reference inputs from config:

- `configs/universe.yaml`
- `configs/theme_nodes.yaml`
- `configs/relationship_edges.yaml`
- `configs/event_taxonomy.yaml`

## Output Datasets

The event layer writes these processed datasets:

- `news_event_entities.parquet`
- `news_event_classifications.parquet`
- `news_event_themes.parquet`
- `news_events_structured.parquet`

DuckDB refreshes after each run, so each dataset is immediately queryable through a view with the same name.

## CLI

Run the event layer directly:

```bash
semicon-alpha event-sync --limit 50
```

Force reprocessing of already-structured articles:

```bash
semicon-alpha event-sync --limit 50 --force
```

`ingest-all` now includes event intelligence after news enrichment, reference sync, and market sync.

## Current Modeling Notes

- Entity extraction is anchored to the curated tracked universe rather than open-ended NER.
- Event classification is config-driven through `configs/event_taxonomy.yaml`.
- Theme mapping blends taxonomy defaults, direct theme keyword hits, and curated company-to-theme relationships.
- Explanations are deterministic strings built from matched signals, mentioned companies, and mapped themes.
- A fallback class `unclassified_semiconductor_event` is included so low-signal but still semiconductor-relevant articles can be retained without silently forcing a bad taxonomy label.

## Why These Outputs Matter

This layer creates the normalized event objects required for the next stages in the project plan:

- graph propagation
- exposure scoring
- lag modeling
- backtesting and evidence views

It is the bridge between raw/enriched article text and the later event-to-impact engine.
