# Phase 2 Wave 1 Terminal Handoff

## Purpose

This document captures the current end-state of the first product-layer build on top of the Phase 1 intelligence engine.

Wave 1 is the analyst workflow MVP:

- backend API over the parquet-first world model
- browser-based terminal shell
- evidence-first event and entity workspaces
- graph path tracing
- lexical retrieval and grounded copilot responses

The goal is to let a new session continue from a working Phase 2 surface without having to rediscover the service boundaries, endpoint shapes, or current product constraints.

## What Exists

The repo now contains a working Wave 1 product layer with these major components:

1. FastAPI application
   - app entrypoint in `src/semicon_alpha/api/main.py`
   - local server command: `semicon-alpha serve`
   - mounted surfaces:
     - `/health`
     - `/terminal`
     - `/api/...`

2. Service layer over the Phase 1 world model
   - `WorldModelRepository` loads the current parquet outputs
   - domain services provide UI-shaped payloads for:
     - dashboard
     - events
     - entities
     - evidence
     - graph exploration
     - search
     - copilot

3. Event workspace
   - event summary
   - ranked impact candidates
   - propagated paths
   - theme mappings
   - supporting evidence
   - competing interpretations
   - lightweight historical analogs

4. Entity workspace
   - entity profile
   - incoming and outgoing graph neighbors
   - recent linked events
   - exposure summary
   - effect pathways
   - relationship and linked-event evidence

5. Graph exploration
   - neighborhood inspection
   - source-to-target path trace using the graph schema traversal rules
   - explainable edge payloads retained in responses

6. Search
   - lexical retrieval across:
     - entities
     - events
     - documents
     - themes

7. Grounded copilot
   - deterministic response layer
   - currently supports:
     - event-scoped questions
     - entity-scoped questions
     - simple entity comparison
     - lightweight weekly-summary prompts
   - citations come from available event or document evidence

8. Browser terminal shell
   - static frontend served from `src/semicon_alpha/ui/terminal/`
   - includes:
     - left rail for search and navigation
     - main workspace pane
     - right context pane for evidence, paths, and copilot

## Storage And Serving Model

Wave 1 does not replace the parquet-first architecture.

- source of truth remains the processed datasets in `data/processed/`
- the API is a serving/query layer over those outputs
- no relational app-state store exists yet
- the frontend is currently read-only relative to the world model

This is intentional. Wave 1 is designed to validate analyst workflows before adding persistent user-state systems for watchlists, boards, alerts, notes, and scenarios.

## Current API Surface

Current routes are:

- `GET /api/dashboard/overview`
- `GET /api/events`
- `GET /api/events/{event_id}`
- `GET /api/events/{event_id}/impacts`
- `GET /api/events/{event_id}/evidence`
- `GET /api/entities/{entity_id}`
- `GET /api/entities/{entity_id}/neighbors`
- `GET /api/entities/{entity_id}/events`
- `GET /api/entities/{entity_id}/effects`
- `POST /api/graph/path-trace`
- `GET /api/search`
- `POST /api/copilot/query`

## Important Modeling Decisions

### API payloads are workspace-shaped

The API does not simply expose raw parquet rows.

Instead, it assembles:

- event workspaces
- entity workspaces
- evidence bundles
- dashboard cards
- path trace payloads

This matches the Phase 2 terminal direction and avoids pushing product assembly complexity into the frontend.

### Evidence degrades gracefully

Wave 1 can still answer event and entity requests even when some optional intermediate datasets are missing.

Examples:

- missing event classifications do not break event workspaces
- missing article-enrichment tables fall back to event-level source metadata

This matters because some development/test contexts only materialize the later Phase 1 outputs.

### Copilot is tool-shaped, not model-shaped

The current copilot layer is intentionally deterministic and grounded in repository services.

It is not yet an LLM orchestration system. The current implementation exists to prove:

- scoped question patterns
- evidence attachment
- related-entity/event suggestions
- the product contract needed for a future richer assistant

## Known Constraints

- No authentication or multi-user support yet.
- No persistent app-state database yet.
- No watchlists, boards, alerts, notes, or scenarios yet.
- Search is lexical, not semantic/vector-based.
- Historical analogs are lightweight and event-type based.
- Copilot answers are heuristic and deterministic, not generative.
- The browser terminal is a focused MVP shell, not the full Phase 2 product spec.

## Verification Status

Verified locally:

- new Wave 1 API integration tests pass
- full test suite passes
- terminal shell loads through the FastAPI app
- dashboard, event, entity, search, path-trace, and copilot endpoints all pass regression coverage

## Recommended Next Step

The next highest-value work is Wave 2 application state and workflow depth:

1. add persistent storage for watchlists, boards, alerts, and notes
2. expand the dashboard into saved views and monitoring workflows
3. strengthen historical analog retrieval and document search
4. replace deterministic copilot heuristics with a tool-routed assistant layer

Wave 1 is now sufficient to demonstrate the end-to-end product loop:

- inspect a recent event
- see ranked affected companies
- trace the propagation path
- review evidence
- pivot into an entity workspace
- ask a grounded follow-up question
