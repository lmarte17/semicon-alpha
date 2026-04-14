# Wave 5 Ontology And Infra Expansion Handoff

## Purpose

This document captures the end-state of the Wave 5 terminal layer:

- ontology expansion beyond companies, themes, and segments
- graph-history snapshots and relationship-change tracking
- hybrid retrieval indexing for terminal search
- terminal/API exposure for ontology browsing and graph history

The goal is to let a new session continue from the current product state without re-deriving how Wave 5 was implemented or where the new data surfaces live.

## What Exists

The repo now contains a working Wave 5 layer on top of the Phase 1 engine and Waves 1 through 4.

### 1. Expanded ontology reference data

Reference sync now loads a new `configs/ontology_nodes.yaml` file and persists:

- `ontology_nodes.parquet`
- `ontology_relationships.parquet`

The current ontology includes:

- countries
- regulators
- technologies
- materials
- capabilities
- facilities

The ontology is still curated/config-driven, which keeps the graph explainable and easy to edit.

### 2. Richer relationship metadata

Relationship records and graph edges now support:

- `effective_start`
- `effective_end`
- `relationship_status`
- `metadata_json`

This is the first step toward time-aware graph inspection. It does not make propagation time-sliced yet, but it does allow the product to show relationship windows and policy metadata.

### 3. Expanded graph build

`src/semicon_alpha/graph/build.py` now:

- reads ontology nodes and ontology relationships
- merges derived country nodes when the company registry introduces countries not already configured
- derives company-to-country location edges when they are not already explicitly configured
- emits graph nodes across:
  - companies
  - themes
  - ontology classes
  - derived segments

The graph remains parquet-first and deterministic.

### 4. Graph-history outputs

`graph-sync` now also writes:

- `graph_node_history.parquet`
- `graph_edge_history.parquet`
- `graph_change_log.parquet`

Current behavior:

- every graph build creates a snapshot of the current node and edge state
- the build diffs current graph state against the previously materialized graph
- added, updated, and removed nodes/edges are written into the change log

This gives the terminal a simple inspection-friendly graph timeline without requiring a separate graph database.

### 5. Hybrid retrieval index

Wave 5 adds `RetrievalIndexService` and `retrieval-sync`.

It materializes:

- `retrieval_index.parquet`

Current shape:

- entities, events, documents, and themes are flattened into search records
- each record stores:
  - semantic text
  - aliases
  - lexical terms
  - deterministic hashed vector embeddings
- search combines lexical overlap and cosine similarity over those local vectors

This is intentionally lightweight. It improves terminal search breadth without forcing external embedding infrastructure.

### 6. API surface

Wave 5 extends the API with:

- `GET /api/entities`
  - list entities by `node_type`
- `GET /api/entities/{entity_id}/history`
  - graph-history and relationship-change feed for a node

The existing search endpoint now uses the retrieval index when present and falls back to lexical search otherwise.

### 7. Entity workspaces are now generic graph-node workspaces

`EntityWorkspaceService` is no longer company-only.

Current behavior:

- company nodes still show score-based exposure summaries
- non-company nodes can now surface recent linked events from graph influence or theme mappings
- effect pathways now work for ontology nodes using retained graph influence paths
- history is included directly in the entity workspace payload

This matters because countries, regulators, facilities, and technologies are now usable product objects rather than background graph data.

### 8. Terminal surface

The browser terminal now exposes:

- a Wave 5-branded shell
- ontology quick-browse controls in the left rail
- ontology directory views by node type
- entity workspace history panels

This is still the same dense pane-based shell, just widened to the expanded ontology.

## Current Modeling Decisions

### Ontology is still curated, not auto-mined

Wave 5 does not introduce automated ontology extraction from documents.

Instead:

- node definitions are explicit in config
- relationships remain config-driven or transparently derived
- graph changes stay inspectable

That is the right tradeoff for the current product stage.

### History is snapshot-based

Graph history is modeled as periodic snapshots plus diffs, not as a fully event-sourced graph ledger.

That keeps implementation local-first and simple while still giving:

- product timelines
- change inspection
- relationship-window display

### Retrieval is hybrid and deterministic

The new retrieval layer is not using a hosted vector database or foundation-model embeddings.

Instead it uses:

- local lexical terms
- deterministic hashed-vector embeddings
- cosine similarity plus lexical scoring

This is enough to materially improve search quality and ontology discoverability while preserving offline/local operation.

## Important Caveats

- The ontology is still modest relative to the long-term spec.
- Time windows exist on relationships, but propagation itself is not yet date-aware.
- Retrieval only indexes entities, events, documents, and themes today. Scenarios and theses are still out of scope for search indexing.
- Workflow observability is still basic and local. There is no dedicated telemetry dashboard yet.
- Graph history is only as granular as graph rebuild cadence.

## Verification Status

Verified locally:

- full test suite passes
- graph build tests now cover ontology nodes and graph-history outputs
- scoring/evaluation tests still pass on top of the expanded graph layer
- Wave 5 API test covers:
  - ontology search
  - entity listing by node type
  - ontology entity workspace loading
  - entity history endpoint

Current local result:

- `python -m pytest -q` passes with `25 passed`

## Recommended Next Step

The next logical step after Wave 5 is not another foundational data layer.

It is product hardening:

1. add scenario/thesis indexing into retrieval
2. add time-aware graph filters in workspaces and path trace
3. add stronger operational observability for search, copilot, and workflow usage
4. decide whether any part of the graph should move beyond parquet/DuckDB based on actual runtime pressure rather than anticipation
