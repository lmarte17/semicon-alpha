# Event Intelligence Layer Handoff

## Purpose

This document captures the current end-state of the Phase 1 Event Intelligence layer so a new session can pick up cleanly and move into the graph, propagation, and scoring work without having to rediscover taxonomy choices, output tables, or pipeline structure.

This work implements the Event Intelligence portion of the product described in [zervehack_semiconductor_project_plan.md](../../zervehack_semiconductor_project_plan.md), specifically the modular bridge between:

- enriched source articles
- structured semiconductor event objects
- inspectable intermediate event-analysis stages
- downstream graph propagation, exposure scoring, and lag modeling

## What Exists

The repo now contains a working Phase 1 Event Intelligence system with these major components:

1. Config-driven event taxonomy
   - Defines the current classifier version
   - Encodes event types, keywords, theme defaults, segment hints, default direction, and base severity
   - Encodes direction-language and severity-language keyword buckets

2. Deterministic article-to-event pipeline
   - Reads `news_articles_enriched.parquet`
   - Uses `news_articles_discovered.parquet` as fallback for missing title/source fields
   - Builds a normalized article context per candidate item

3. Tracked-company extraction
   - Anchors entity extraction to the curated semiconductor universe in `configs/universe.yaml`
   - Builds alias sets from company names, tickers, simplified names, and a small manual alias map
   - Produces explicit origin-company and mentioned-company outputs

4. Event-type classification
   - Scores each taxonomy event type against article title/body content
   - Incorporates segment and theme support from the curated reference layer
   - Retains all candidate scores in an intermediate table rather than only the winning label

5. Theme and segment mapping
   - Maps themes from:
     - taxonomy defaults
     - direct theme-keyword matches
     - curated company-to-theme relationship edges
   - Derives primary and secondary segments from entity and taxonomy evidence

6. Structured event output
   - Produces normalized event records with:
     - headline
     - source
     - published timestamp
     - origin companies
     - mentioned companies
     - primary segment
     - secondary segments
     - primary themes
     - event type
     - direction
     - severity
     - confidence
     - market relevance score
     - deterministic summary and reasoning text

7. CLI integration and query-layer refresh
   - Adds `semicon-alpha event-sync`
   - Adds event processing into `semicon-alpha ingest-all`
   - Refreshes DuckDB views after each event run

## Storage Model

The Event Intelligence layer follows the same Phase 1 storage model already established for ingestion:

- raw source artifacts remain under `data/raw/`
- normalized analytical datasets are stored as parquet under `data/processed/`
- DuckDB at `data/semicon_alpha.duckdb` exposes the processed event datasets as queryable views

This keeps the layer aligned with the overall product-plan requirements:

- deterministic outputs
- inspectable intermediate stages
- provenance-preserving inputs
- easy local validation before later graph/scoring layers

## Current Modeling Decisions

### Entity extraction

- Entity extraction is intentionally bounded to the curated tracked universe.
- This is not open-ended NER yet.
- The goal is high interpretability against the initial semiconductor company set rather than broad recall.

### Taxonomy strategy

- Classification is config-driven through `configs/event_taxonomy.yaml`.
- The current taxonomy covers the initial event categories called out in the project plan, plus a fallback `unclassified_semiconductor_event` bucket.
- The fallback bucket exists so low-signal but still semiconductor-relevant items do not get silently forced into the wrong class.

### Direction and severity

- Direction uses deterministic keyword buckets plus taxonomy defaults.
- Severity uses deterministic keyword buckets plus taxonomy base severity, with light escalation when multiple origin names and strong event evidence appear together.
- This is intentionally simple and explainable for the MVP.

### Theme mapping

- Theme mapping is hybrid but still deterministic.
- It combines:
  - taxonomy-declared theme defaults
  - direct theme-keyword hits
  - curated company-to-theme relationship edges

### Confidence and market relevance

- Both are heuristic scores derived from:
  - classification strength
  - classification margin
  - entity evidence
  - theme evidence
  - text availability
  - severity
- They are not trained model probabilities.

## Core Output Datasets

The Event Intelligence layer now produces these primary parquet datasets:

- `news_event_entities.parquet`
- `news_event_classifications.parquet`
- `news_event_themes.parquet`
- `news_events_structured.parquet`

DuckDB also exposes these through views in:

- `data/semicon_alpha.duckdb`

## CLI Commands

The current CLI now supports:

- `semicon-alpha news-snapshot`
- `semicon-alpha news-enrich --limit 25`
- `semicon-alpha event-sync --limit 50`
- `semicon-alpha reference-sync`
- `semicon-alpha market-sync --start YYYY-MM-DD`
- `semicon-alpha ingest-all --start YYYY-MM-DD --enrich-limit 25 --event-limit 50`
- `semicon-alpha db-sync`

## Alignment With The Product Plan

Relative to the Event Intelligence requirements in the project plan, the current implementation satisfies the following core needs:

1. Structured event-object generation
   - We now convert enriched articles into normalized event records
   - The outputs include event type, direction, severity, confidence, summary, and reasoning

2. Explicit intermediate stages
   - Entity extraction, classification, and theme mapping are separated and persisted
   - The pipeline is inspectable instead of opaque

3. Semiconductor-specific framing
   - Entity extraction is tied to the curated semiconductor universe
   - Taxonomy classes and theme mapping remain semiconductor-specific

4. Explainability requirement
   - The system stores event-type candidate scores
   - The system stores matched entity mentions and theme mappings
   - Final event records include deterministic summary and reasoning fields

5. Modular downstream readiness
   - The output shape is suitable for the next graph/propagation and scoring layers
   - The layer does not entangle itself with graph logic yet

This means the repo is now in a good position to start the next core solution layer.

## Important Implementation Details

- Structured event records are written with stable `event_id` values derived from `article_id`.
- `news_articles_discovered.parquet` is used as fallback context when enriched articles lack title or site fields.
- Alias generation includes company-name simplification and a small hand-maintained alias list for important names like TSMC, ASE, and ASML.
- Theme mapping depends partly on the curated company-to-theme relationships in `configs/relationship_edges.yaml`.
- The current live dataset may still produce events with zero tracked company mentions if the article is semiconductor-adjacent but outside the curated universe.

## Verification Status

Verified locally:

- new end-to-end Event Intelligence test passes
- full test suite passes
- `semicon-alpha event-sync --force` runs successfully against the current local processed data
- event parquet outputs are written and visible to DuckDB

The layer is stable enough to move into the next stage.

## Recommended Next Step

Begin the graph / influence modeling and exposure layer.

The next session should focus on turning `news_events_structured` plus the curated relationship tables into a graph-ready propagation substrate, likely starting with:

1. graph node and edge assembly
2. neighborhood and path tracing utilities
3. event-to-theme and event-to-company propagation logic
4. explicit first-order / second-order / third-order exposure decomposition
5. explanation-path outputs suitable for later scoring and UI evidence views

The Event Intelligence layer is already shaped to support that work.
