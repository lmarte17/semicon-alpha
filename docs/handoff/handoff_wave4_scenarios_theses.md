# Wave 4 Scenario And Thesis Workflow Handoff

## Purpose

This document captures the end-state of the Wave 4 terminal layer:

- scenario workspaces
- explicit scenario assumptions and monitors
- deterministic scenario runs over the current graph/world model
- thesis objects and confidence updates
- thesis monitoring and contradiction/support alerts

The goal is to let a new session continue product work from the current state without rediscovering how forward-looking workflows are represented or how they connect back to the Phase 1 engine.

## What Exists

The repo now contains a working Wave 4 layer on top of the earlier terminal waves.

### 1. App-state objects

`src/semicon_alpha/appstate/repository.py` now persists:

- scenarios
- scenario assumptions
- scenario monitors
- scenario runs
- theses
- thesis links
- thesis updates

Alerts were also extended to carry:

- `scenario_ids_json`
- `thesis_ids_json`

This lets alert routing and workspace loading stay first-class for the new objects.

### 2. Scenario service

Implemented in `src/semicon_alpha/services/scenarios.py`.

Current behavior:

- scenarios are created from explicit typed assumptions
- default monitors are created from those assumptions unless custom monitors are provided
- graph-backed assumptions (`entity`, `theme`, `segment`) run deterministic propagation over the existing graph edges
- historical assumptions (`event_type`, `event`) derive ranked impacts from historical event-score outputs and retained top paths
- runs persist:
  - ranked impacted entities
  - affected paths
  - support signals
  - contradiction signals
  - run summary text

This keeps scenario outputs assumption-driven and path-backed rather than speculative.

### 3. Thesis service

Implemented in `src/semicon_alpha/services/theses.py`.

Current behavior:

- theses store:
  - title
  - statement
  - stance
  - confidence
  - status
  - time horizon
- theses can link to:
  - entities
  - themes
  - event types
  - events
  - scenarios
- theses maintain explicit update history
- thesis monitoring reuses:
  - scenario monitor signals for linked scenarios
  - recent event/score evidence for linked entities/themes/event types/events

### 4. Alert expansion

`AlertService` now generates:

- `scenario_support`
- `scenario_invalidation`
- `thesis_support`
- `thesis_contradiction`

These are still deterministic and fingerprinted, just like the earlier watchlist and contradiction alerts.

### 5. Report expansion

`ReportService` now supports:

- `scenario_memo`
- `thesis_change_report`

These remain deterministic structured briefs, persisted in app state and exported to markdown like the earlier report types.

### 6. API surface

Wave 4 adds:

- `GET /api/scenarios`
- `POST /api/scenarios`
- `GET /api/scenarios/{id}`
- `POST /api/scenarios/{id}/run`
- `GET /api/theses`
- `POST /api/theses`
- `GET /api/theses/{id}`
- `POST /api/theses/{id}/updates`

The copilot and report-generation request models were also extended to accept `scenario_id` and `thesis_id`.

### 7. Terminal surface

The browser terminal now exposes:

- scenario creation in the left rail
- thesis creation in the left rail
- scenario list in the left rail
- thesis list in the left rail
- scenario workspace in the main pane
- thesis workspace in the main pane
- scenario re-run action in the scenario workspace
- scenario/thesis-aware alert navigation
- scenario memo and thesis change report generation from the shared report panel
- notes attached to scenarios and theses through the existing note flow

## Current Modeling Decisions

### Scenarios are explicit, not chat-native

The core design constraint from the spec is preserved:

- no free-form scenario chat as the system of record
- scenario state begins with explicit assumptions
- outputs are derived from graph traversal or historical impact evidence
- runs are saved as inspectable records

### Assumptions are typed around the current ontology

Supported assumption types today are:

- `entity`
- `theme`
- `segment`
- `event_type`
- `event`

This is intentionally narrower than the long-term spec and matches the ontology that already exists in the current graph/world model.

### Scenario propagation uses the current graph rules

Wave 4 does not introduce a separate scenario graph engine.

Instead it reuses:

- current graph nodes and edges
- current graph-schema traversal rules
- current sign semantics
- historical event-score outputs where the assumption is event-like rather than node-like

That keeps scenario reasoning aligned with the rest of the product.

### Thesis monitoring is evidence-driven

Current thesis monitoring is based on:

- linked scenario signals
- linked entity score flow
- linked theme / segment / event-type event flow
- explicit thesis update history

This is enough to make theses operational without adding a separate belief engine.

## Important Caveats

- Scenario assumptions are still limited to the current ontology.
- Scenario runs are deterministic and path-backed, but they are not counterfactual simulations over full market history.
- There is no scenario branching tree or version graph yet.
- Thesis collaboration, sharing, approval, and multi-user workflow are not implemented.
- Thesis confidence updates are explicit user updates, not automatically re-scored beliefs.
- Search does not yet index scenarios or theses as first-class lexical search results.
- Scenario and thesis alerts are generated on refresh, not by a background scheduler.

## Verification Status

Verified locally:

- new Wave 4 API tests pass
- prior Wave 1 through Wave 3 tests still pass
- full test suite passes
- scenario creation auto-produces a saved run
- thesis creation supports direct item links and scenario links
- Wave 4 alerts appear in the existing alert feed
- scenario memo and thesis change report generation both export markdown files

## Recommended Next Step

The next logical step is Wave 5:

1. widen the ontology
2. add richer scenario objects around countries, regulators, facilities, and technologies
3. add stronger search/retrieval for scenario and thesis discovery
4. add relationship-history tracking and time-aware graph inspection
5. evaluate whether semantic retrieval or a graph database is justified by runtime/product needs
