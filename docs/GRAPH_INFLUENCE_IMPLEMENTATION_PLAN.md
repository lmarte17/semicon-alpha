# Graph / Influence Modeling Implementation Plan

## Goal

Implement the graph / influence modeling layer as the next Phase 1 core module after Event Intelligence.

The graph should act as a knowledge-and-inference substrate for:

- company-to-company dependency reasoning
- company-to-theme and company-to-segment exposure reasoning
- event-to-impact propagation across first-, second-, and third-order paths
- explainable path tracing for later scoring and UI layers

## Recommended Design

The best fit for the current repo is:

1. parquet as the canonical graph data store
2. DuckDB as the local query layer
3. a typed edge table as the source of truth
4. an in-memory graph representation for neighborhood/path queries
5. a custom deterministic propagation engine rather than generic graph-library scoring

This is better than jumping straight to Neo4j or another hosted graph database because the project is still in the MVP / local-iteration stage and already uses parquet + DuckDB effectively.

## Why This Is The Right Approach

### What the repo already has

The repo already has the exact inputs a first graph layer needs:

- `company_registry.parquet`
- `company_relationships.parquet`
- `theme_nodes.parquet`
- `theme_relationships.parquet`
- `news_events_structured.parquet`
- `news_event_themes.parquet`
- optional `news_event_entities.parquet`

The missing piece is not storage infrastructure. The missing piece is a normalized graph assembly layer plus event-driven propagation logic.

### Why not a graph database yet

A graph database would add operational complexity before the semantics are stable.

Right now the hard problem is:

- edge semantics
- traversal rules
- sign propagation
- event anchoring
- path explainability

Those should be settled in code and datasets first. If needed, a graph database can come later.

### Why not rely only on NetworkX

NetworkX is useful for:

- neighborhood exploration
- simple path tracing
- quick visualization/debugging

But the actual propagation logic should be custom, because the project needs:

- edge-type-specific traversal rules
- signed path behavior
- depth-aware decay
- deterministic explainability
- stable tests over scoring behavior

## Core Implementation Principles

1. Keep the edge table first-class.
2. Separate graph construction from propagation.
3. Treat event anchoring as a distinct dataset.
4. Keep propagation deterministic before introducing learned models.
5. Preserve path-level explainability for every propagated result.
6. Allow theme-first events even when no tracked company is directly mentioned.

That last point matters because the current live Event Intelligence data can already produce theme-only events.

## Data Model Recommendation

### 1. Graph nodes

Create a unified `graph_nodes.parquet` with one row per node.

Suggested columns:

- `node_id`
- `node_type`
- `label`
- `description`
- `source_table`
- `ticker`
- `segment_primary`
- `metadata_json`
- `is_active`
- `created_at_utc`

Initial node types:

- `company`
- `theme`
- `segment`

Notes:

- `theme_nodes.parquet` already gives you `technology`, `demand_driver`, `bottleneck`, and `segment`-like themes under a common theme abstraction.
- The company registry also has segment values that are not currently first-class nodes.
- The graph build should therefore synthesize `segment:<name>` nodes from `segment_primary` and `segment_secondary`.

### 2. Graph edges

Create a unified `graph_edges.parquet` with one row per directed edge.

Suggested columns:

- `edge_id`
- `source_node_id`
- `target_node_id`
- `source_node_type`
- `target_node_type`
- `edge_type`
- `weight`
- `sign`
- `confidence`
- `evidence`
- `evidence_url`
- `last_updated`
- `source_table`
- `is_derived`

Sources of edges:

1. existing `company_relationships.parquet`
2. existing `theme_relationships.parquet`
3. derived company-to-segment membership edges from `company_registry.parquet`

Recommended derived edge types:

- `in_segment_primary`
- `in_segment_secondary`

These membership edges should be low-friction and explicit, because they make segment-level propagation possible without overloading theme edges.

### 3. Event anchors

Create `event_graph_anchors.parquet`.

This should convert structured events into graph starting points.

Suggested columns:

- `event_id`
- `anchor_node_id`
- `anchor_node_type`
- `anchor_role`
- `anchor_score`
- `anchor_direction`
- `anchor_confidence`
- `anchor_reason`
- `processed_at_utc`

Recommended anchor sources:

1. origin companies from `news_events_structured`
2. mentioned companies from `news_events_structured`
3. primary themes from `news_events_structured`
4. theme rows from `news_event_themes`
5. primary/secondary segments when company anchors are missing or weak

Recommended anchor roles:

- `origin_company`
- `mentioned_company`
- `primary_theme`
- `secondary_theme`
- `primary_segment`

### 4. Propagation paths

Create `event_propagation_paths.parquet`.

This is the most important graph output for explainability.

Suggested columns:

- `event_id`
- `target_node_id`
- `target_node_type`
- `hop_count`
- `path_rank`
- `path_nodes`
- `path_edges`
- `path_score`
- `path_direction`
- `path_confidence`
- `reason_codes`
- `processed_at_utc`

### 5. Raw propagated node scores

Create `event_node_influence.parquet`.

This should be the graph layer’s aggregated output before the later exposure-scoring layer turns company candidates into final ranked impact scores.

Suggested columns:

- `event_id`
- `node_id`
- `node_type`
- `best_hop_count`
- `path_count`
- `direct_path_score`
- `first_order_score`
- `second_order_score`
- `third_order_score`
- `aggregate_influence_score`
- `provisional_direction`
- `confidence`
- `top_paths`

## Graph Construction Recommendation

### Build step

Add a graph builder that:

1. loads company registry
2. loads theme nodes
3. creates synthetic segment nodes
4. merges company and theme relationship tables into one typed edge table
5. adds derived company-to-segment membership edges
6. writes `graph_nodes.parquet`
7. writes `graph_edges.parquet`

### In-memory representation

Use `networkx.MultiDiGraph` in memory for graph inspection and path tracing.

Why `MultiDiGraph`:

- multiple relationship types may exist between the same nodes
- edge identity matters for explainability
- it matches the typed-edge-table design

But do not make NetworkX the source of truth. Rebuild it from `graph_edges.parquet` whenever needed.

## Propagation Recommendation

### Do not use generic shortest-path scoring

This project needs typed, signed, and depth-aware propagation. That is better handled with a custom traversal engine.

### Recommended propagation algorithm

Use a bounded beam/BFS-style traversal:

1. seed frontier from `event_graph_anchors`
2. traverse up to depth 3
3. compute propagated score at each step using explicit rule tables
4. keep the strongest few paths per target node
5. aggregate results by target node after traversal

Recommended depth behavior:

- depth 1 = direct / first-order
- depth 2 = second-order
- depth 3 = third-order

### Recommended score shape

For each step:

`step_score = prior_score * edge_weight * edge_confidence * traversal_multiplier * hop_decay`

Where:

- `edge_weight` comes from the edge table
- `edge_confidence` comes from the edge table
- `traversal_multiplier` comes from edge-type rules
- `hop_decay` might be something like:
  - 1.00 at hop 1
  - 0.65 at hop 2
  - 0.45 at hop 3

### Sign and direction handling

Do not try to solve full causal sign logic in one pass.

Instead use a clear rule table:

- `positive` edges preserve sign
- `negative` edges invert sign
- `mixed` edges attenuate confidence and may produce `mixed`
- `competitor_to` should usually invert sign
- `supplier_to` and `dependent_on` usually preserve sign but depend on traversal direction

This should live in config, not hard-coded all over the codebase.

## Traversal Semantics Recommendation

The edge table should remain business semantics.

Traversal semantics should be defined separately in a config such as `configs/graph_schema.yaml`.

Suggested config concepts per edge type:

- `forward_multiplier`
- `reverse_multiplier`
- `default_sign_behavior`
- `allows_reverse_traversal`
- `confidence_penalty`
- `max_depth_preference`

Example logic:

- `dependent_on`
  - strong reverse traversal from dependency target back to dependent company
  - medium forward traversal

- `supplier_to`
  - allow both supplier -> customer and customer -> supplier traversal
  - use different multipliers for each direction

- `competitor_to`
  - lower confidence than dependency edges
  - sign inversion default

- `benefits_from`
  - strong theme -> company traversal
  - weaker company -> theme reverse traversal

- `exposed_to`
  - preserve sign but with lower certainty than direct dependency edges

## Event Anchoring Recommendation

The graph layer should not require origin companies to exist.

Anchor priority should be:

1. origin companies
2. primary themes
3. mentioned companies
4. primary segment
5. secondary themes / segments

Anchor score should use:

- event confidence
- market relevance score
- theme match score
- whether the anchor came from origin vs mention vs theme inference

This prevents the graph from failing on theme-heavy or policy-heavy events.

## Repo Structure Recommendation

Add a new graph package:

```text
src/semicon_alpha/graph/
  __init__.py
  build.py
  propagate.py
  query.py
  rules.py
```

Recommended responsibilities:

- `build.py`
  - node and edge assembly
  - graph dataset writes

- `rules.py`
  - traversal rule loading
  - sign behavior helpers

- `propagate.py`
  - event anchor generation
  - bounded traversal
  - path and node influence outputs

- `query.py`
  - neighborhood lookup
  - path tracing
  - graph object construction from parquet

## CLI Recommendation

Add:

- `semicon-alpha graph-sync`
- `semicon-alpha graph-propagate --limit N`

`graph-sync` should:

- build `graph_nodes.parquet`
- build `graph_edges.parquet`
- refresh DuckDB

`graph-propagate` should:

- build `event_graph_anchors.parquet`
- run propagation for current structured events
- write `event_propagation_paths.parquet`
- write `event_node_influence.parquet`
- refresh DuckDB

Do not yet combine graph propagation with market evaluation or ranking. Keep the layers separated.

## Testing Recommendation

Add tests in this order:

1. graph build test
   - company + theme + segment nodes created correctly
   - relationship tables merged correctly

2. traversal-rule test
   - edge types apply expected forward/reverse multipliers
   - competitor edges invert sign

3. anchor-generation test
   - events with companies create company anchors
   - theme-only events still create usable anchors

4. propagation test
   - depth-limited traversal produces expected first-/second-/third-order candidates
   - top paths are stable and inspectable

5. aggregation test
   - node influence scores aggregate correctly across multiple paths

## Build Order Recommendation

The cleanest implementation order is:

1. add graph record models
2. add `configs/graph_schema.yaml`
3. implement `graph-sync`
4. write `graph_nodes.parquet` and `graph_edges.parquet`
5. implement event anchor generation
6. implement bounded propagation
7. write path and node influence outputs
8. add tests
9. only then move into exposure scoring

## Strong Recommendation

The best implementation is a hybrid:

- typed parquet graph datasets as source of truth
- NetworkX `MultiDiGraph` for query ergonomics
- custom deterministic propagation for actual influence modeling

That gives the project:

- interpretability
- modularity
- fast local iteration
- explainable paths
- clean compatibility with the current repo architecture

It is the most defensible next step from the codebase as it exists today.
