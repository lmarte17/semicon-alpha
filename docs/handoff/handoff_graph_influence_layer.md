# Graph / Influence Modeling Layer Handoff

## Purpose

This document captures the current end-state of the Phase 1 Graph / Influence Modeling layer so a new session can pick up cleanly and move into exposure scoring and lag modeling without having to rediscover graph-shape decisions, propagation semantics, or output datasets.

This work implements the graph portion of the product described in [zervehack_semiconductor_project_plan.md](../../zervehack_semiconductor_project_plan.md), specifically the modular bridge between:

- structured semiconductor events
- typed ecosystem graph datasets
- deterministic first-, second-, and third-order propagation
- explainable path outputs for later scoring and UI layers

## What Exists

The repo now contains a working Phase 1 Graph / Influence Modeling system with these major components:

1. Unified graph node dataset
   - Builds `graph_nodes.parquet`
   - Includes:
     - company nodes from `company_registry`
     - theme nodes from `theme_nodes`
     - derived segment nodes synthesized from company registry metadata

2. Unified graph edge dataset
   - Builds `graph_edges.parquet`
   - Includes:
     - company-to-company edges from `company_relationships`
     - company-to-theme edges from `theme_relationships`
     - derived company-to-segment membership edges

3. Config-driven traversal semantics
   - Uses `configs/graph_schema.yaml`
   - Encodes:
     - max depth
     - hop decay
     - beam width
     - top-path retention
     - per-edge-type forward/reverse traversal multipliers
     - per-edge-type sign behavior

4. Event anchoring
   - Builds `event_graph_anchors.parquet`
   - Anchors from:
     - origin companies
     - mentioned companies
     - event themes
     - primary and secondary segments
   - Supports theme-first events even when no tracked company is directly mentioned

5. Deterministic propagation engine
   - Traverses the graph up to depth 3
   - Produces:
     - path-level outputs in `event_propagation_paths.parquet`
     - aggregated node-level outputs in `event_node_influence.parquet`
   - Preserves path nodes, path edges, score, direction, confidence, and reason codes

6. In-memory graph query support
   - Builds a `networkx.MultiDiGraph` from the parquet node/edge datasets
   - Supports neighborhood inspection for debugging and future UI/query use

7. CLI integration
   - Adds `semicon-alpha graph-sync`
   - Adds `semicon-alpha graph-propagate --limit N`

## Storage Model

The graph layer follows the same Phase 1 storage model already established for earlier layers:

- normalized analytical datasets live under `data/processed/`
- DuckDB at `data/semicon_alpha.duckdb` exposes the graph and propagation outputs as views

The important design decision is:

- parquet datasets are the graph system of record
- the in-memory graph is rebuilt from parquet when needed

This keeps the layer inspectable, testable, and aligned with the repo’s current architecture.

## Current Modeling Decisions

### Graph storage strategy

- Not using a dedicated graph database yet
- Typed node and edge parquet files remain the canonical graph data assets
- DuckDB remains the local analytical query layer

### Node strategy

- `company` and `theme` nodes come directly from the curated reference layer
- `segment` nodes are synthesized so segment-level event anchoring and propagation work explicitly

### Edge strategy

- Relationship tables remain first-class source data
- Segment-membership edges are derived instead of implied implicitly in code
- Reverse traversal behavior is controlled by config rather than by physically duplicating reverse edges in the stored dataset

### Propagation strategy

- Propagation is deterministic and bounded
- Depth 1 maps to first-order
- Depth 2 maps to second-order
- Depth 3 maps to third-order
- Traversal uses edge weights, edge confidence, edge-type multipliers, and hop decay

### Sign and direction strategy

- Direction is carried from the anchored event
- Edge sign handling is controlled by rule config
- `competitor_to` is treated as sign-inverting
- `mixed` edges degrade directional confidence

### Theme-first event support

- The graph layer does not require origin companies to exist
- This matters because Event Intelligence can already generate valid theme-heavy events with zero tracked company mentions

## Core Output Datasets

The graph layer now produces these primary parquet datasets:

- `graph_nodes.parquet`
- `graph_edges.parquet`
- `event_graph_anchors.parquet`
- `event_propagation_paths.parquet`
- `event_node_influence.parquet`

DuckDB also exposes these through views in:

- `data/semicon_alpha.duckdb`

## CLI Commands

The current CLI now supports:

- `semicon-alpha graph-sync`
- `semicon-alpha graph-propagate --limit 50`

Alongside the previously existing:

- `semicon-alpha news-snapshot`
- `semicon-alpha news-enrich --limit 25`
- `semicon-alpha event-sync --limit 50`
- `semicon-alpha reference-sync`
- `semicon-alpha market-sync --start YYYY-MM-DD`
- `semicon-alpha db-sync`

## Alignment With The Product Plan

Relative to the graph / influence modeling requirements in the project plan, the current implementation satisfies the following core needs:

1. Typed graph substrate
   - We now have unified graph nodes and edges
   - Company-to-company and company-to-theme relationships are both supported

2. Deterministic propagation logic
   - Events can now be turned into graph anchors
   - The system can propagate across first-, second-, and third-order paths

3. Explainable intermediate outputs
   - Anchors are stored explicitly
   - Path outputs are stored explicitly
   - Node-level aggregate influence is stored explicitly

4. Config-driven traversal semantics
   - Edge-type behavior is governed by `configs/graph_schema.yaml`
   - Traversal logic is not scattered across unrelated code paths

5. Modular downstream readiness
   - The graph layer produces exactly the kind of path and node outputs the scoring layer needs next

This means the repo is now in a good position to begin exposure scoring.

## Important Implementation Details

- `graph_edges.parquet` stores only the source-of-truth directed edges; reverse traversal is handled at runtime by propagation rules.
- `graph-propagate` can work on theme-only events because anchors are allowed to come from `news_event_themes` and segment fields.
- `event_node_influence.parquet` includes company, theme, and segment nodes; later scoring should filter or weight node types appropriately.
- `event_graph_anchors` and propagation outputs are separate from final ranked market-impact tables on purpose; the scoring layer still needs to convert raw influence into impact scores.

## Verification Status

Verified locally:

- new graph-layer tests pass
- full test suite passes
- `graph-sync` runs successfully against the current local processed datasets
- `graph-propagate --force` runs successfully against the current local processed datasets
- graph parquet outputs are written and visible to DuckDB

The layer is stable enough to move into the next stage.

## Recommended Next Step

Begin the exposure scoring layer.

The next session should focus on converting `event_node_influence` plus event metadata into company-ranked impact candidates, likely starting with:

1. company-only filtering and ranking views
2. explicit first-order / second-order / third-order score decomposition
3. provisional impact direction handling
4. obviousness penalties for origin names
5. explanation-path selection for each ranked company

The graph layer is already shaped to support that work.
