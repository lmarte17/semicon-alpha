# Wave 2 / Wave 3 Operational Monitoring And Reporting Handoff

## Purpose

This document captures the end-state of the next terminal layers built after the Wave 1 read-only analyst shell:

- Wave 2 operational monitoring
- Wave 3 historical intelligence and reporting

The goal is to let a new session continue from the current product layer without rediscovering how app-state persistence, alert generation, historical analogs, or report payloads are currently implemented.

## What Exists

The repo now contains a working local-first application state layer and the first operational/research workflows on top of the Phase 1 engine.

### 1. Local app-state repository

Implemented in `src/semicon_alpha/appstate/repository.py`.

Current SQLite-backed state includes:

- watchlists
- watchlist items
- boards
- board items
- notes
- saved queries
- alerts
- reports

The database lives at:

- `data/app_state.sqlite`

### 2. Wave 2 operational services

Current service modules include:

- `WatchlistService`
- `BoardService`
- `NotesService`
- `SavedQueryService`
- `AlertService`

These sit on top of the existing parquet-first world model and do not replace it.

### 3. Wave 3 research services

Current research/reporting modules include:

- `ResearchService`
- `ReportService`

These build:

- richer event analog retrieval
- event backtest workspaces
- structured report payloads
- markdown report exports

### 4. API surface

New API routes now include:

- `GET/POST /api/watchlists`
- `GET /api/watchlists/{id}`
- `POST /api/watchlists/{id}/items`
- `DELETE /api/watchlists/items/{item_id}`
- `GET/POST /api/boards`
- `GET /api/boards/{id}`
- `POST /api/boards/{id}/items`
- `GET/POST /api/notes`
- `GET /api/alerts`
- `POST /api/alerts/refresh`
- `POST /api/alerts/{id}/dismiss`
- `GET/POST /api/queries`
- `GET /api/queries/{id}/run`
- `GET /api/events/{id}/analogs`
- `GET /api/events/{id}/backtest`
- `GET/POST /api/reports`
- `GET /api/reports/{id}`

### 5. Terminal surface

The browser terminal now exposes:

- watchlists in the left rail
- boards in the left rail
- active alerts in the left rail
- saved queries in the left rail
- workflow controls for adding the current context to a watchlist or board
- contextual notes / annotations in the right panel
- report generation and report browsing in the right panel
- board and watchlist workspaces in the main pane
- event analog and backtest sections in the event workspace

## Current Modeling Decisions

### App state is local-first

This implementation intentionally uses SQLite rather than introducing a networked database.

Why:

- the repo is still local-first
- Wave 2/3 workflows are user-state oriented, not high-throughput transactional systems
- this keeps delivery aligned with the existing single-user desktop/dev workflow

### Alerts are explainable and deterministic

The current alert engine supports these first-pass alert types:

1. watch event alerts
   - generated when a watched entity/theme/event type/segment matches an event

2. score signal alerts
   - generated when a watched entity’s rank score clears a meaningful threshold relative to prior linked scores

3. contradiction alerts
   - generated when a note with a directional stance conflicts with newer entity/theme evidence

Alerts are deduplicated with stable fingerprints in SQLite.

### Boards are saved thematic workspaces

Boards currently support saved items of types such as:

- entity
- event
- theme
- report
- query-like references

They also aggregate:

- board notes
- board-linked reports
- board event feeds
- board-relevant alerts

### Historical analogs are similarity-scored, not embedding-based

Wave 3 analog retrieval is still deterministic.

Current similarity features include:

- same event type
- same direction
- same severity
- same primary segment
- shared themes
- shared impacted companies

This is enough for a credible product surface without adding semantic retrieval yet.

### Backtest view is event-centric

The current backtest workspace merges:

- predicted impact candidates from `event_impact_scores`
- realized market outcomes from `event_market_reactions`

This gives users a concrete predicted-vs-realized inspection surface directly in the product layer.

### Reports are deterministic briefs with persistence

Current supported report types are:

- `event_impact_brief`
- `weekly_thematic_brief`
- `entity_comparison_brief`

Reports are:

- persisted in app state
- returned by API
- exported to markdown files under `outputs/reports/`

## Important Caveats

- App state is still single-user and local.
- Alerts are generated on demand through the API today, not by a background scheduler.
- Relationship-change and structural-centrality alerts from the long-term spec are not implemented yet.
- Saved queries currently support only the global lexical search path.
- Historical analog retrieval is still heuristic, not semantic/vector-based.
- Reports are template-driven and deterministic, not LLM-generated.
- Board collaboration and sharing are not implemented.

## Verification Status

Verified locally:

- new Wave 2 / Wave 3 API tests pass
- existing Wave 1 API tests still pass
- full test suite passes
- report generation writes markdown exports
- alerts, watchlists, boards, saved queries, analogs, and backtest payloads all pass regression coverage

## Recommended Next Step

The next highest-value work is Wave 4:

1. scenario workspace
2. explicit assumption objects
3. scenario run outputs over graph context
4. thesis monitoring
5. invalidation alerts

The current product layer is now strong enough to support that move because it already has:

- persistent user state
- monitoring surfaces
- explainable alerting
- historical comparison
- product-facing reporting
