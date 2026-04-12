# Phase 2 Specification: Intelligence Terminal / Analyst OS

## Purpose

Phase 2 transforms the Phase 1 intelligence engine into a usable product: a domain-specific **intelligence terminal** that feels directionally inspired by Bloomberg and Palantir, but is purpose-built for semiconductor, supply-chain, macro-industrial, and geopolitical intelligence.

This phase is **not** about building a generic market terminal, a generic chatbot, or a graph visualization toy. It is about building an **analyst operating system** on top of the Phase 1 graph, event extraction, and effect-propagation engine.

The terminal should allow a user to:

- ask natural-language questions across the intelligence graph and source corpus
- inspect companies, suppliers, fabs, countries, technologies, materials, and policy bodies as first-class entities
- trace first-, second-, and third-order effects from major events
- understand why something matters and how impact may propagate
- create watchlists, alerts, and saved workspaces
- run scenario analysis against the graph and event network
- generate analyst-quality briefs with provenance and explainability

The goal is to convert Phase 1 from “interesting infrastructure” into a product that supports real analytical work.

---

## Core Product Thesis

### Product framing

Phase 2 is best described as:

> An intelligence operating system for understanding how important events propagate through complex industrial and market networks.

This gives the project a strong and realistic identity.

It should feel:

- **Bloomberg-like** in information density, linked panels, watchlists, drill-downs, timelines, and event monitoring
- **Palantir-like** in ontology, connected objects, provenance, workflow support, traceability, and operational reasoning
- **Differentiated** by its causal/effects layer: not only showing what happened, but what it likely affects next and why

### What this is not

This phase should explicitly avoid becoming:

- a general-purpose market data terminal
- a pure chat-over-documents assistant
- a graph-only product with weak workflows
- a broad “intelligence for everything” platform on day one
- a generic RAG demo with semiconductors as decoration

### Initial domain focus

Phase 2 should remain tightly focused on the Phase 1 domain:

- semiconductors
- semiconductor equipment
- advanced packaging
- AI infrastructure supply chain
- industrial dependencies
- macro and geopolitical policy impacts

Expansion to adjacent domains can come later, but the ontology and workflows should be optimized for the initial domain first.

---

## Relationship to Phase 1

Phase 1 builds the **world model**.

Phase 2 builds the **user interface and workflow layer** for interacting with that world model.

### Phase 1 responsibilities

Phase 1 should already be responsible for most or all of the following:

- ingesting structured and unstructured sources
- extracting entities, events, and relationships
- building or updating the ontology-backed graph
- scoring relationship strength and confidence
- computing first-, second-, and third-order effect candidates
- storing provenance and evidence links
- maintaining document and event history over time

### Phase 2 responsibilities

Phase 2 should build product features on top of those outputs:

- analyst-facing UI
- entity and event workspaces
- graph exploration
- copilot interactions
- watchlists and alerts
- scenario analysis
- briefing/report generation
- saved boards and collaboration primitives

### Architectural separation

A clean separation is important.

- **Phase 1 = Intelligence Engine**
- **Phase 2 = Analyst OS / Terminal Layer**

This keeps the system modular and allows improvements to extraction, scoring, propagation, and ontology design without rewriting the product layer.

---

## Product Vision

The terminal should help a user answer questions like:

- What changed this week in the AI semiconductor supply chain?
- Which companies are most exposed to this event?
- Why does this policy change matter?
- What are the likely second-order effects of a packaging bottleneck?
- Which relationships in the network have strengthened or weakened over the last 30 days?
- Show me who depends on this supplier and what breaks if capacity falls.
- Compare Samsung and SK hynix exposure to AI memory demand.
- Generate a portfolio-manager brief on foundry, memory, and packaging implications.
- What contradictory evidence exists against the current thesis?

### Primary users

Initial users may include:

- domain analysts
- research professionals
- technology investors
- strategy teams
- journalists or policy researchers
- power users monitoring industrial systems and supply chains

### User promise

A user should be able to move from:

- raw event
- to affected entities
- to downstream pathways
- to evidence
- to generated brief
- to tracked thesis

in one system, without manually hopping across tabs, notes, spreadsheets, and generic search tools.

---

## Product Pillars

The terminal should be built around five pillars.

### 1. Ontology-driven entity understanding

The system should treat entities as first-class objects with rich relationships, not merely strings in documents.

Examples:

- companies
- business units
- fabs
- foundries
- equipment vendors
- chip designers
- countries and regulatory bodies
- technologies and process nodes
- materials and packaging capabilities
- customers and suppliers

### 2. Event-to-impact reasoning

This is the core differentiator.

The terminal should not stop at event summarization. It should model how events propagate through relationships and time horizons.

### 3. Evidence-backed explainability

Every assertion, impact path, and generated conclusion should trace back to source evidence and internal reasoning metadata.

### 4. Workflow-native analysis

The terminal should support actual work:

- research exploration
- briefing creation
- watchlist monitoring
- thesis validation
- scenario analysis
- note capture

### 5. Human-readable intelligence outputs

The system should translate graph complexity into analyst-readable outputs without hiding the underlying structure.

---

## Conceptual Product Modules

Phase 2 should contain the following major modules.

### A. Entity Workspace

Each major object in the ontology should have an entity page.

#### Purpose

Give users a stable “home” for each entity where they can understand role, dependencies, recent changes, and exposure.

#### Example entity types

- company
- supplier
- fab
- regulator
- technology
- product family
- country
- facility
- material

#### Entity page sections

Each entity page should aim to include:

1. **Profile**
   - name
   - type
   - description
   - tags/themes
   - role in ecosystem

2. **Recent developments**
   - recent events linked to the entity
   - timeline of noteworthy changes
   - event classifications and severity

3. **Relationship map**
   - upstream dependencies
   - downstream customers / dependent entities
   - strategic partners
   - policy dependencies
   - competitor cluster

4. **Exposure summary**
   - event exposure
   - concentration risk
   - dependency hotspots
   - strategic bottlenecks

5. **Effect pathways**
   - outgoing likely effects
   - incoming likely risks
   - first-, second-, and third-order connections

6. **Evidence & sources**
   - linked articles
   - filings
   - transcripts
   - extracted facts
   - confidence metadata

7. **Copilot panel**
   - ask questions scoped to this entity
   - summarize recent changes
   - compare against another entity
   - explain importance in the ecosystem

#### Design principle

Entity pages must feel operational, not encyclopedic.

The page should answer “why this matters now,” not only “what this is.”

---

### B. Event Workspace

Each major event should have its own page/workspace.

#### Purpose

Enable users to inspect a material event and move from description to propagation.

#### Example event types

- export control policy change
- earnings call commentary
- fab outage
- earthquake near industrial cluster
- capex shift
- packaging bottleneck
- product launch
- regulatory action
- shipment restriction
- labor strike
- geopolitical escalation

#### Event page sections

1. **Event summary**
   - what happened
   - when it happened
   - why it is notable
   - confidence / source diversity

2. **Primary affected entities**
   - direct entities named in or linked to the event

3. **Impact candidates**
   - likely first-order effects
   - likely second-order effects
   - possible third-order effects
   - confidence and time horizon

4. **Propagation paths**
   - relationship chains showing how the event may move through the network

5. **Competing interpretations**
   - bullish vs bearish
   - short-term vs long-term
   - contradictory evidence

6. **Supporting evidence**
   - source documents
   - extracted snippets
   - structured facts
   - citation provenance

7. **Copilot / scenario actions**
   - summarize impact
   - compare to similar events
   - generate analyst memo
   - add to watchlist
   - start scenario branch

#### Design principle

Users should never be stranded at “summary.”

Every event should open a path into impact analysis.

---

### C. Graph & Relationship Explorer

#### Purpose

Give users a way to navigate the underlying graph interactively.

#### What the graph is for

The graph is an **analysis instrument**, not a decorative visual.

It should support:

- seeing relationship types
- inspecting strength/weight/confidence
- filtering by time, type, or theme
- identifying bottlenecks and hubs
- tracing impact paths
- drilling into evidence

#### Key features

- neighborhood exploration for any entity/event
- path tracing between two nodes
- filtering by relationship type
- filtering by recency
- filtering by confidence or influence score
- timeline overlay to show relationship changes over time
- click-through to evidence and entity/event pages

#### Important constraint

Do not let the product devolve into “look at this graph.”

The graph must always connect back to analysis tasks.

---

### D. Copilot / Analyst Interaction Layer

#### Purpose

Allow users to query the world model in natural language and receive evidence-backed, structured responses.

#### Example queries

- What changed this week in HBM supply?
- Who is most exposed to this export control update?
- Compare TSMC and Samsung in advanced packaging positioning.
- Why does this event matter to Nvidia’s supply chain?
- What are the likely downstream effects if CoWoS constraints persist for two more quarters?
- Which companies gained strategic importance in the graph this month?

#### Copilot capabilities

The copilot should be able to:

- search documents and graph context
- retrieve entity/event neighborhoods
- compare entities
- explain relationship significance
- summarize recent changes
- generate analytical memos
- perform scenario-based reasoning
- surface uncertainty and contradictory evidence

#### Response requirements

Responses should be:

- evidence-backed
- structured when appropriate
- explicit about uncertainty
- linked to entities, events, and sources
- separated into observations vs inferences

#### Design principle

This should feel like a serious analytical interface, not a friendly general chatbot.

---

### E. Watchlists, Alerts, and Boards

#### Purpose

Turn the terminal into an operational monitoring environment.

#### Watchlists

Users should be able to watch:

- entities
- sectors/themes
- relationships
- event types
- geographies
- supply-chain segments

#### Alerts

Examples:

- New event linked to watched entity
- Relationship strength changed materially
- Contradictory evidence emerged for active thesis
- Cluster centrality shifted in watched network
- A dependency concentration exceeded threshold
- Scenario assumptions invalidated by new data

#### Saved boards / workspaces

Users should be able to create persistent views for:

- AI supply chain
n- advanced packaging
- memory market
- China export controls
- foundry competition
- geopolitical risk

Each board can include:

- selected entities
- recent events
- graph filters
- custom notes
- saved copilot queries
- generated reports

---

### F. Scenario Analysis Workspace

#### Purpose

Support counterfactual and forward-looking analysis.

#### Example prompts

- Assume CoWoS capacity remains constrained for two more quarters.
- Assume export controls broaden to include advanced packaging tools.
- Assume memory pricing rises 15% over the next quarter.
- Assume a major foundry delays 2nm ramp.

#### Scenario outputs

The system should generate:

- affected entities and clusters
- most likely impact pathways
- likely winners / losers / bottlenecks
- confidence levels
- variables to monitor
- contradictory assumptions
- comparison against baseline world state

#### Design principle

Scenario analysis should be tied to explicit assumptions and graph pathways, not free-form speculation.

---

## UX Direction

The terminal should borrow interface ideas from high-density analyst tools.

### Overall interface philosophy

- pane-based
- information-dense
- entity-first
- fast switching between summary and detail
- traceable and inspectable
- optimized for users doing real analytical work

### Suggested primary layout

A likely layout could include:

1. **Left navigation rail**
   - watchlists
   - boards
   - saved searches
   - alerts
   - ontology categories

2. **Central workspace**
   - entity page / event page / scenario page / search results / board

3. **Right-side context panel**
   - copilot
   - evidence viewer
   - impact paths
   - notes / annotations

4. **Top global search bar**
   - entities
   - events
   - documents
   - themes
   - commands

### Key views to prioritize

- global dashboard
- entity view
- event view
- graph/path explorer
- scenario lab
- watchlist board
- briefing/report view

### UX anti-patterns to avoid

- oversized “pretty graph first” landing page
- chat-only interface with hidden structure
- too many disconnected tabs without shared state
- no provenance inspection
- overwhelming users with raw extraction noise

---

## Core User Workflows

The product should be designed around a small number of powerful workflows.

### Workflow 1: Event triage

1. User sees a new event in dashboard or alert feed.
2. Opens event page.
3. Reviews summary and direct entities.
4. Inspects first-, second-, and third-order impact candidates.
5. Opens affected entity pages.
6. Asks copilot for concise interpretation.
7. Saves memo or adds entities to watchlist.

### Workflow 2: Entity deep-dive

1. User searches for a company or technology.
2. Opens entity page.
3. Reviews role, dependencies, recent developments, and exposure summary.
4. Opens graph explorer for neighborhood.
5. Runs compare flow against peer entity.
6. Generates one-page briefing.

### Workflow 3: Weekly research brief

1. User opens a thematic board like “Advanced Packaging.”
2. Reviews top events and network changes from the past week.
3. Uses copilot prompt to summarize changes.
4. Pulls in supporting evidence automatically.
5. Generates a structured analyst note.
6. Saves/export note to knowledge base or report system.

### Workflow 4: Scenario analysis

1. User creates a scenario assumption.
2. System branches baseline graph context into scenario mode.
3. Propagation engine generates impact candidates and paths.
4. Copilot explains scenario implications.
5. User saves scenario and attaches monitor variables.
6. Watchlist tracks whether real-world events validate or invalidate the scenario.

### Workflow 5: Thesis monitoring

1. User creates or imports a thesis.
2. Links thesis to entities, events, and assumptions.
3. System watches for relevant new signals.
4. Alerts user on supportive or contradictory evidence.
5. User updates thesis confidence over time.

---

## System Architecture

The following architecture assumes Phase 1 already exists or is partially built.

### Layer 1: Data ingestion and normalization

Sources may include:

- news feeds
- company press releases
- SEC filings
- earnings transcripts
- policy documents
- government publications
- industry reports
- internal notes / curated analyst documents

Responsibilities:

- pull documents/events
- normalize metadata
- deduplicate
- store raw artifacts
- send items for extraction

### Layer 2: Extraction and enrichment

Responsibilities:

- entity extraction
- event extraction
- relationship extraction
- fact extraction
- sentiment / stance / relevance classification
- time horizon classification
- confidence scoring

Outputs:

- structured entities
- structured events
- structured relations
- evidence spans
- enrichment metadata

### Layer 3: Ontology and world model

Responsibilities:

- canonicalize objects
- map aliases to canonical IDs
- enforce ontology types
- maintain relationship taxonomy
- track object versioning over time

Stores:

- graph database or graph-like relational model
- document store
- event store
- vector index for retrieval

### Layer 4: Propagation and scoring engine

Responsibilities:

- compute first-order effects
- infer second-/third-order candidates
- score relationship influence
- model confidence and time horizon
- identify bottlenecks, hubs, and dependencies

This engine is the heart of the causal layer.

### Layer 5: Application / orchestration layer

Responsibilities:

- serve UI data
- manage copilot tool calls
- execute workflow logic
- enforce access patterns
- handle caching and user state

### Layer 6: Terminal UI layer

Responsibilities:

- render pages and panels
- support navigation and drill-downs
- expose watchlists, boards, alerts
- allow report generation and saved workflows

---

## Recommended Technical Components

The exact stack can vary, but the system should roughly include the following.

### Backend

- Python backend
- FastAPI or equivalent API framework
- async workers for ingestion and enrichment
- job queue for extraction / graph updates / report generation

### Storage

- PostgreSQL for canonical relational data and application state
- graph database (Neo4j, Memgraph, or graph model in Postgres) for relationships
- object storage for raw docs/artifacts
- vector index for semantic retrieval

### AI / LLM layer

- model provider for extraction / summarization / copilot workflows
- structured output support
- prompt templates for each workflow
- tool-calling layer for graph/document/query access

### Frontend

- React / Next.js
- component library suited for dense data UIs
- graph visualization library
- timeline and table components

### Observability

- event logs
- prompt traces
- tool execution logs
- evaluation harness
- alerting for ingestion/extraction failures

---

## Ontology Guidance

A strong ontology is essential.

### Initial object classes

Suggested first-pass classes:

- Company
- BusinessUnit
- Facility / Fab
- Country / Region
- PolicyBody / Regulator
- Product
- TechnologyNode
- PackagingCapability
- Material
- EquipmentType
- Event
- Theme / Narrative
- Document / Source
- Thesis
- Scenario

### Relationship examples

- SUPPLIES
- DEPENDS_ON
- COMPETES_WITH
- REGULATED_BY
- PRODUCES
- FABRICATES_FOR
- SHIPS_TO
- ENABLES
- CONSTRAINS
- LOCATED_IN
- IMPACTS
- EXPOSED_TO
- SUBSTITUTE_FOR
- ANNOUNCED_IN
- EVIDENCED_BY

### Relationship metadata

Every relationship should support metadata such as:

- confidence score
- strength / weight
- direction
- relationship type
- effective time window
- evidence links
- update timestamp
- source diversity count

### Design note

Do not overbuild the ontology at the beginning.

Start with a smaller number of clear object types and relation types, then expand as real use cases demand more expressiveness.

---

## Copilot Architecture

The copilot should not be a single monolithic prompt.

It should be an orchestrated layer with tools.

### Copilot responsibilities

- intent classification
- query decomposition
- graph retrieval
- document retrieval
- evidence ranking
- structured answer generation
- uncertainty handling
- citation formatting

### Suggested tool set

The copilot should be able to call tools such as:

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
- `run_scenario(assumptions)`

### Output patterns

Different workflows should produce different output shapes.

Examples:

- concise answer with citations
- comparison table
- event impact tree
- one-page memo
- scenario summary
- monitored thesis update

### Important principle

The system should separate:

- **facts observed in sources**
- **inferences from graph and propagation logic**
- **generated summaries for user readability**

That distinction is critical for trust.

---

## Alerts and Monitoring Design

The alert system is a major differentiator because it operationalizes the intelligence model.

### Alert categories

1. **Event alerts**
   - new material event for watched entity/theme

2. **Relationship alerts**
   - dependency strength changed
   - new critical linkage inferred

3. **Contradiction alerts**
   - new evidence conflicts with active thesis or scenario

4. **Structural alerts**
   - cluster centrality or bottleneck metrics changed

5. **Scenario alerts**
   - monitored variable moved beyond threshold
   - scenario assumption weakened or supported

### Delivery surfaces

- in-app notification center
- board-level alert feed
- entity/event page banners
- optional outbound notifications later

### Alert quality requirements

Each alert should include:

- why it triggered
- affected entities
- confidence / severity
- supporting evidence
- suggested next action

---

## Briefing and Report Generation

Generated outputs should be one of the most tangible product features.

### Report types

Suggested initial report types:

- daily/weekly thematic brief
- event impact brief
- entity comparison brief
- supply-chain risk brief
- scenario memo
- thesis change report

### Report structure

A report should generally include:

1. Executive summary
2. Key events / observations
3. Impact analysis
4. Affected entities and pathways
5. Contradictory evidence / uncertainty
6. What to watch next
7. Source appendix / provenance

### Design principle

Reports should feel like analyst work product, not generic AI prose.

---

## Explainability and Trust

This product will only be credible if users can inspect why the system thinks what it thinks.

### Trust mechanisms

- citations to source evidence
- explicit confidence levels
- distinction between observed facts and inferred impacts
- path visualization for propagation
- contradictory evidence surfacing
- time horizon labeling
- recency indicators

### Example confidence language

- high confidence direct effect
- moderate confidence second-order pathway
- low confidence speculative third-order scenario candidate

### Required user controls

Users should be able to:

- inspect evidence behind a relationship
- inspect evidence behind an event summary
- hide low-confidence inferences
- compare current and prior graph state

---

## MVP vs Full Phase 2

This document describes the full Phase 2 vision, but development should still be staged.

### Phase 2A: Core terminal foundation

Build first:

- entity pages
- event pages
- basic graph/path explorer
- copilot over graph + docs
- watchlists
- simple briefing generation

### Phase 2B: Operational intelligence

Add next:

- alerts
- saved boards
- compare workflows
- more sophisticated propagation views
- richer provenance tooling

### Phase 2C: Advanced reasoning layer

Add later:

- scenario workspace
- thesis tracking
- contradiction monitoring
- collaborative notes / annotations
- scenario invalidation alerts

This phased approach keeps delivery practical without weakening the long-term vision.

---

## Suggested Repo / Service Structure

A coding agent should have a clear mental model of how to organize this work.

```text
phase2/
  README.md
  docs/
    product_vision.md
    ontology.md
    ux_principles.md
    workflows.md
    api_contracts.md
  frontend/
    app/
    components/
    features/
      dashboard/
      entities/
      events/
      graph/
      copilot/
      watchlists/
      reports/
      scenarios/
  backend/
    api/
    services/
      entities/
      events/
      graph/
      propagation/
      copilot/
      alerts/
      reports/
      scenarios/
    models/
    schemas/
    workers/
  prompts/
    entity_summary/
    event_summary/
    impact_analysis/
    comparison/
    briefing/
    scenario/
  evals/
    copilot/
    extraction/
    propagation/
    reports/
  shared/
    types/
    constants/
```

### Service boundaries

At minimum, keep these service concerns distinct:

- entity service
- event service
- graph service
- propagation service
- copilot service
- watchlist/alert service
- reporting service
- scenario service

---

## Example API Surface

Illustrative endpoints only:

- `GET /entities/{id}`
- `GET /entities/{id}/neighbors`
- `GET /entities/{id}/events`
- `GET /entities/{id}/effects`
- `GET /events/{id}`
- `GET /events/{id}/impacts`
- `POST /graph/path-trace`
- `POST /copilot/query`
- `POST /reports/generate`
- `POST /watchlists`
- `GET /alerts`
- `POST /scenarios`
- `POST /scenarios/{id}/run`

Responses should be designed for UI usability and provenance visibility, not just backend convenience.

---

## Evaluation Strategy

Because this project relies on extraction, graph construction, and generated reasoning, evaluation must be explicit.

### What to evaluate

1. **Extraction quality**
   - entity precision / recall
   - event extraction correctness
   - relationship labeling accuracy

2. **Canonicalization quality**
   - alias resolution
   - duplicate collapse

3. **Propagation quality**
   - relevance of first-order candidates
   - usefulness of second-/third-order candidates
   - false positive rate

4. **Copilot quality**
   - factual accuracy
   - citation grounding
   - appropriate uncertainty handling
   - output usefulness

5. **Report quality**
   - clarity
   - evidence coverage
   - analytical usefulness

### Evaluation methods

- curated gold examples
- analyst review loops
- regression tests for key workflows
- prompt evaluation harnesses
- failure taxonomies and incident review

---

## Risks and Failure Modes

A coding agent should understand these risks from the beginning.

### Product risks

- the graph becomes visually impressive but analytically shallow
- the copilot feels generic and untrustworthy
- provenance is too weak for serious users
- ontology is either too thin or too complex
- alerts become noisy and ignored

### Technical risks

- entity canonicalization errors pollute the graph
- relationship inference creates cascading false positives
- scenario engine becomes hand-wavy without disciplined assumptions
- performance suffers under graph-heavy interactive queries

### Mitigations

- prioritize explainability early
- keep ontology intentionally narrow at first
- label confidence explicitly
- separate observed facts from inferred impact
- build with evaluation harnesses from the beginning

---

## Product Positioning

This project should **not** be pitched as a Bloomberg competitor.

It should be positioned as:

> A domain-specific intelligence terminal for understanding how events propagate through complex industrial and market networks.

That framing is stronger because it is:

- more defensible
- more original
- more achievable
- more aligned to the actual product advantage

### Strong positioning statement

A Bloomberg-style terminal gives users access to information.
A Palantir-style ontology gives users a connected world model.
This project adds a third layer: **event-to-impact reasoning**.

That is the differentiator.

---

## Future Expansion Path

Once the semiconductor-first version works, the same product pattern can expand into adjacent domains.

### Adjacent domain opportunities

- AI infrastructure
- energy and power systems
- commodities and industrials
- geopolitics and industrial policy
- public equities thematic intelligence
- logistics and manufacturing bottlenecks

The key requirement for expansion is ontology maturity and credible event-to-impact modeling in each domain.

---

## Implementation Guidance for Coding Agents

A coding agent working from this spec should internalize the following priorities.

### Priority order

1. Make entity and event pages useful.
2. Make the copilot grounded in the world model.
3. Make provenance visible everywhere.
4. Make graph exploration task-oriented.
5. Add operational features like watchlists and alerts.
6. Add scenario and thesis tooling after the basics are solid.

### Non-negotiables

- Do not implement a chat-only shell and call it Phase 2.
- Do not make the graph the only major UI artifact.
- Do not hide evidence.
- Do not merge observed facts and speculative inference.
- Do not generalize the ontology too early.

### What “good” looks like

A strong first usable Phase 2 build should let a user:

- open an entity and immediately understand why it matters
- open an event and trace likely downstream effects
- ask a question and get a grounded, citeable answer
- generate a concise brief from recent changes
- monitor a watchlist for meaningful shifts

If those five things work well, the system will already feel like a real product.

---

## Final Summary

Phase 2 is the moment where the project evolves from an intelligence engine into an intelligence product.

The core idea is to build a **domain-specific intelligence terminal** that combines:

- ontology-backed entities
- event-centered workflows
- graph-based relationship reasoning
- effect propagation
- analyst copilot workflows
- watchlists, alerts, and boards
- scenario and thesis support
- strong explainability and provenance

The result should feel like a Bloomberg/Palantir-inspired analyst operating system for semiconductors and industrial intelligence — not because it imitates them directly, but because it combines dense information access, connected world modeling, and operational decision support around a focused domain.

That is the right Phase 2.
