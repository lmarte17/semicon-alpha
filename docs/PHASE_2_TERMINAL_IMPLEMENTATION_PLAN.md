# Phase 2 Intelligence Terminal Implementation Plan

## Purpose

This document turns the product goals in [PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md](../PHASE_2_INTELLIGENCE_TERMINAL_SPEC.md) into an implementation sequence that fits the current repo state.

The guiding principle is:

- build the narrowest serious analyst workflow first
- keep every layer grounded in the existing Phase 1 world model
- expand in waves until the full Phase 2 spec is covered

This plan assumes the current Phase 1 engine already exists and remains the source of truth for:

- structured events
- graph propagation
- lag predictions
- ranked impact scores
- realized market-reaction evaluation

## Current Readiness

The repo is ready to begin Phase 2 because the following engine outputs already exist:

- `news_events_structured.parquet`
- `graph_nodes.parquet`
- `graph_edges.parquet`
- `event_propagation_paths.parquet`
- `event_node_influence.parquet`
- `event_lag_predictions.parquet`
- `event_impact_scores.parquet`
- `event_market_reactions.parquet`
- `evaluation_summary.parquet`

What does **not** exist yet is the Phase 2 product-serving layer:

- backend API
- UI-facing query/view models
- persistent application state
- evidence-serving layer
- global search
- copilot orchestration
- watchlists / alerts / boards
- scenario workflows
- report generation

That gap is exactly what this plan addresses.

## Delivery Strategy

Build Phase 2 in two levels:

1. **Core Sequence**
   - the minimum product slice that turns the engine into a usable analyst workflow

2. **Expansion Waves**
   - additional modules that progressively close the gap with the full spec

This avoids trying to build the full analyst OS in one jump while still preserving alignment with the original vision.

## Core Sequence

The core sequence should be built in this order.

### 1. Backend API layer

#### Goal

Expose the current world model through a product-facing API rather than CLI-only workflows.

#### Why first

Nothing in Phase 2 should read parquet files directly from the UI. The API becomes the stable boundary between the intelligence engine and the product layer.

#### Deliverables

- FastAPI app under `src/semicon_alpha/api/`
- typed response schemas
- service layer that reads DuckDB / parquet-backed data
- health/status endpoint
- versioned API routes

#### Minimum endpoints

- `GET /health`
- `GET /dashboard/overview`
- `GET /events`
- `GET /events/{event_id}`
- `GET /events/{event_id}/impacts`
- `GET /entities/{entity_id}`
- `GET /entities/{entity_id}/neighbors`
- `GET /entities/{entity_id}/events`
- `POST /graph/path-trace`

#### Notes

- keep the initial API read-only
- do not block on auth or multi-user complexity
- design responses for UI usability, not raw dataset dumping

### 2. UI-facing view models

#### Goal

Translate raw engine tables into product-ready shapes for dashboards, entity workspaces, and event workspaces.

#### Why second

The Phase 1 datasets are good analytical assets, but the Phase 2 UI needs curated composite payloads rather than one-table-at-a-time reads.

#### Deliverables

- dashboard feed view
- event workspace view
- entity workspace view
- path trace view
- evidence bundle view

#### Example composite outputs

**Event workspace**
- event summary
- primary affected entities
- ranked first-/second-/third-order candidates
- predicted lag windows
- top propagation paths
- supporting sources and reasoning
- historical realized examples when available

**Entity workspace**
- profile
- role in ecosystem
- neighbor summary by relationship type
- recent linked events
- top incoming / outgoing effects
- recent evaluated hits and misses

### 3. Provenance and evidence layer

#### Goal

Make the terminal trustworthy by exposing evidence everywhere.

#### Why third

The spec is explicit that Phase 2 fails if provenance is weak. A dashboard without inspectable evidence becomes a glossy wrapper over hidden logic.

#### Deliverables

- evidence service for events, relationships, and paths
- explicit separation of:
  - observed facts
  - inferred impacts
- snippet extraction for source support
- source appendix payloads for event/entity pages

#### Needed additions

- event-to-article evidence bundles
- relationship evidence lookup
- path-level evidence stitching
- source diversity counts where possible

### 4. Search and retrieval

#### Goal

Provide the global search bar and retrieval layer required by the terminal UX.

#### Why fourth

The event and entity workspaces can ship without semantic search at first, but the terminal cannot scale into daily analyst use without a unified search layer.

#### Deliverables

- lexical search over:
  - entities
  - events
  - themes
  - documents
- filtered search by date, theme, event type, relationship type
- result grouping for entity/event/document scopes

#### Later extension

- semantic retrieval / vector index
- analog-event retrieval
- contradiction retrieval

### 5. Persistent app-state layer

#### Goal

Store user and workspace state needed for actual workflows.

#### Why fifth

Read-only pages can ship first. Watchlists, alerts, boards, notes, and saved queries require app-state storage and should be introduced once the core read model is stable.

#### Deliverables

- relational app database
- tables for:
  - watchlists
  - watchlist_items
  - boards
  - board_items
  - alerts
  - notes
  - saved_queries

#### Technical note

Do not migrate the Phase 1 world model into a new database as part of this step.

Use:

- parquet + DuckDB for the analytical world model
- relational DB for product/application state

### 6. Copilot orchestration layer

#### Goal

Add a grounded copilot that works through tools over the world model instead of acting like a generic chatbot.

#### Why sixth

The copilot should sit on top of stable APIs and evidence-serving tools, not substitute for them.

#### Deliverables

- copilot service
- intent routing
- tool-call layer
- prompt templates by workflow
- structured response types

#### Initial tool set

- `search_entities(query)`
- `get_entity(entity_id)`
- `get_entity_neighbors(entity_id, filters)`
- `search_events(query, time_range, filters)`
- `get_event(event_id)`
- `trace_path(source_id, target_id, constraints)`
- `get_effect_candidates(event_id or entity_id)`
- `search_documents(query, filters)`
- `get_evidence_for_relation(relation_id)`
- `compare_entities(entity_a, entity_b)`
- `generate_brief(scope, time_range)`

## Expansion Waves

After the core sequence ships, expand in waves.

## Wave 1: Analyst Workflow MVP

### Product scope

Ship the narrowest serious terminal experience:

- global dashboard
- event workspace
- entity workspace
- graph/path explorer
- right-side evidence panel
- basic copilot panel

### Target workflows

- event triage
- entity deep-dive

### Required components

- backend API
- view models
- evidence layer
- lexical search
- frontend shell

### Success criteria

- a user can open an event and move from summary to ranked impacts to top paths to evidence
- a user can open an entity page and inspect role, neighbors, recent events, and exposure summary
- a user can ask a grounded copilot question and receive an evidence-backed answer

### What is intentionally deferred

- boards
- alerts
- scenario workspace
- collaboration
- generated reports beyond a simple memo response

## Wave 2: Operational Monitoring

### Product scope

Add the workflow layer that makes the terminal operational rather than exploratory.

### Modules

- watchlists
- alerts
- saved boards
- saved queries
- notes / annotations

### Alert types to support first

- new event linked to watched entity
- new event linked to watched theme
- meaningful score change for watched impact candidates
- contradiction alert when new evidence conflicts with active interpretation

### Success criteria

- users can create and manage watchlists
- users can save a thematic board
- users receive explainable alerts with linked entities, events, and evidence

## Wave 3: Historical Intelligence and Reporting

### Product scope

Make the terminal useful for weekly research and analyst brief creation.

### Modules

- historical analog retrieval
- richer event comparison
- one-click brief generation
- backtest/evidence workspace
- report export payloads

### Why this wave matters

The Phase 1 engine now has scored impacts and realized evaluations. This wave turns those into trust-building product experiences.

### Success criteria

- users can compare a current event to earlier similar events
- users can inspect what the system predicted versus what actually happened
- users can generate a structured memo with citations and impact candidates

## Wave 4: Scenario and Thesis Workflows

### Product scope

Add the forward-looking reasoning layer from the spec.

### Modules

- scenario workspace
- scenario assumptions
- scenario run engine over baseline graph context
- thesis objects
- thesis monitoring
- scenario invalidation alerts

### Important constraint

Scenarios must remain assumption-driven and path-backed. Do not implement free-form speculative chat as the scenario system.

### Success criteria

- users can create a scenario from explicit assumptions
- the system can run a scenario branch and show affected entities and paths
- the system can monitor whether later evidence supports or invalidates the scenario/thesis

## Wave 5: Ontology and Infra Expansion

### Product scope

Close the remaining gap between the MVP terminal and the full long-term spec.

### Main expansions

- more ontology classes:
  - fabs
  - facilities
  - countries
  - regulators
  - technologies
  - packaging capabilities
  - materials
- richer relationship metadata and time windows
- graph-history / relationship-change tracking
- semantic retrieval and vector search
- optional graph database adoption if runtime needs justify it
- observability for prompts, tool use, and workflow performance

### When to do this

Only after the core product workflows are working. Do not front-load graph-database migration or ontology explosion before the first usable terminal exists.

## Recommended Technical Shape

### Backend

- FastAPI for API surface
- service modules grouped by product concern:
  - dashboard
  - entities
  - events
  - graph
  - evidence
  - search
  - copilot
  - watchlists
  - alerts
  - scenarios
  - reports

### Storage

Use a hybrid model:

- Phase 1 world model remains parquet + DuckDB for now
- application state goes into PostgreSQL or SQLite-first if you want to stay local initially
- raw documents remain on disk/object storage
- add vector retrieval only when semantic search is actually needed

### Frontend

- Next.js / React
- dense pane-based layout
- entity-first routing
- right-side context panel for:
  - evidence
  - paths
  - copilot
  - notes

## Proposed Repo Expansion

Suggested additions that fit the existing codebase:

```text
src/semicon_alpha/
  api/
    main.py
    schemas.py
    routes/
      dashboard.py
      entities.py
      events.py
      graph.py
      copilot.py
      watchlists.py
      alerts.py
      scenarios.py
  services/
    dashboard.py
    entities.py
    events.py
    evidence.py
    search.py
    reports.py
  copilot/
    orchestrator.py
    tools.py
    prompts.py
  appstate/
    models.py
    repository.py
  ui/
    terminal/...
```

## Suggested Milestones

### Milestone A: Read-only terminal shell

- API for dashboard, events, entities, graph
- frontend shell
- event and entity pages
- path explorer
- evidence panel

### Milestone B: Grounded copilot

- tool-based copilot on top of the API
- memo / comparison outputs
- structured observations vs inferences responses

### Milestone C: Operational workflow layer

- watchlists
- alerts
- boards
- notes

### Milestone D: Historical research layer

- analog events
- backtest view
- reporting

### Milestone E: Scenario and thesis layer

- scenario workspace
- thesis monitoring
- invalidation alerts

### Milestone F: Full-spec expansion

- ontology growth
- relationship history
- semantic retrieval
- optional graph-db move

## Practical Recommendation

If the goal is to start building immediately without losing the full-spec vision, the best first implementation slice is:

1. FastAPI backend
2. dashboard + event workspace + entity workspace
3. graph/path explorer
4. evidence panel
5. basic grounded copilot

That slice is large enough to feel like the Phase 2 product and small enough to ship before the operational features.

## Anti-Goals For The First Phase 2 Slice

Do not start with:

- a graph-only landing page
- a chat-only product
- a full scenario system
- a full graph-database migration
- a huge ontology expansion
- complex collaboration primitives

Those are later-wave concerns.

## Recommended Immediate Next Step

Begin **Wave 1 / Milestone A**.

Concretely:

1. create the FastAPI app and schemas
2. implement event and entity read endpoints
3. implement graph/path-trace and evidence endpoints
4. scaffold the frontend shell around dashboard, event page, and entity page

That is the shortest path from the current Phase 1 engine to a real Phase 2 terminal.
