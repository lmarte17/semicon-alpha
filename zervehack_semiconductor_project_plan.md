# ZerveHack Project Plan: Semiconductor News Propagation Engine

## Working Title

**When Semiconductor News Breaks, Who Gets Hit Next?**

Alternative internal title:
**Semiconductor Shock Propagation Engine**

---

## Core Hackathon Question

**Which semiconductor companies are most likely to experience delayed, underpriced second- and third-order market reactions after major industry news breaks?**

This is the **research and product question** we are building around.

### Important clarification
We are **not** putting the word **graph** in the question.  
The graph is part of the **solution architecture**, not the question itself.

---

## What We Are Building

We are building a system that:

1. Ingests semiconductor industry news
2. Converts raw news into structured events
3. Uses a **relationship graph / influence graph** of the semiconductor ecosystem under the hood
4. Estimates which companies are exposed through first-, second-, and third-order effects
5. Predicts which names are likely to react **later** rather than immediately
6. Compares predicted delayed movers against realized market reactions
7. Exposes the result through a usable app and optionally an API

This is **not** just a sentiment tool.
This is **not** just a stock prediction model.
This is **not** just a network visualization.

This is an **event intelligence + propagation + delayed-reaction detection** system for the semiconductor market.

---

## Why This Project Fits the Hackathon

This project is aligned with the hackathon because it has:

- A sharp question
- Clear analytical depth
- A compelling end-to-end workflow
- A natural deployed artifact
- A strong story for why AI-native data tooling matters

It should feel like something that is difficult to build well with a static notebook alone.

The strongest part of the project is that it aims to uncover **non-obvious downstream and adjacent market effects**, not simply classify whether news is positive or negative.

---

## Product Thesis

Markets often react quickly to the obvious name in a headline, but more slowly to connected companies that are affected indirectly.

Examples:
- Export controls affecting equipment vendors, foundries, and downstream designers differently
- Hyperscaler AI demand affecting GPU makers, HBM memory suppliers, advanced packaging, substrates, networking, and power management
- Foundry or node ramp changes affecting fabless customers, suppliers, and competitor positioning
- Memory pricing shifts affecting AI infrastructure economics and server supply chain names

The goal is to identify:

- **what happened**
- **who is obviously impacted**
- **who else is likely impacted**
- **how strongly**
- **in what direction**
- **on what lag**
- **before the market fully prices it**

---

## Solution Overview

At a high level:

**News -> Event Understanding -> Graph-Based Exposure Propagation -> Delayed-Reaction Scoring -> Backtest / Evaluation -> App/API**

The graph is a core internal modeling component.

### Internal graph concept

We will model the semiconductor ecosystem as a graph of entities and relationships.

#### Nodes may include:
- Public semiconductor companies
- Segments
- Technologies
- Bottlenecks
- Supply chain functions
- Demand drivers

#### Example company nodes:
- NVIDIA
- AMD
- Intel
- TSMC
- Samsung
- Micron
- SK hynix
- ASML
- Applied Materials
- Lam Research
- KLA
- Broadcom
- Marvell
- Qualcomm
- Synopsys
- Cadence
- ASE
- Amkor

#### Example segment/functional nodes:
- Advanced packaging
- HBM
- Foundry capacity
- Leading-edge logic
- Memory pricing
- AI server demand
- EUV equipment
- Wafer fab equipment
- EDA
- Networking
- Analog/power
- Substrates

#### Example edge types:
- supplier_to
- customer_of
- competitor_to
- dependent_on
- constrained_by
- benefits_from
- exposed_to
- correlated_with
- demand_flows_to
- bottleneck_for

Each edge should support at least:
- direction
- strength / weight
- relationship type
- optional confidence
- optional sign (positive / negative / mixed, where useful)

The graph is not just for visualization. It is the engine for propagation and scoring.

---

## User-Facing Product Behavior

A user should be able to input or select a major semiconductor news event and receive:

- A structured summary of the event
- The most obviously impacted companies
- The most likely delayed second-order companies
- The most likely delayed third-order companies
- Expected direction of impact
- Expected lag window
- Explanation for each prediction
- Historical analogs or similar prior events
- Evidence of how the system performed on past events

The app should answer this practical question:

**A major semiconductor event happened. Which less-obvious names are most likely to react next, and why?**

---

## System Objectives

### Primary objective
Predict and rank semiconductor companies that are likely to experience **delayed, underpriced second- and third-order reactions** after a major industry event.

### Secondary objectives
- Build a reusable event ontology for semiconductor news
- Encode ecosystem dependencies into a machine-usable graph
- Estimate lag behavior by company and event type
- Backtest whether propagated exposure actually maps to later abnormal returns
- Deploy a demoable tool in Zerve

---

## Scope Guidance

This project should remain semiconductor-focused.

Do **not** broaden it into:
- all technology stocks
- macroeconomics generally
- all commodities
- generic finance news

We are borrowing the **propagation / hidden-effects** framing from commodity shock analysis, but the domain is **semiconductors**.

---

## Research Question and Product Tagline

### Final research question
**Which semiconductor companies are most likely to experience delayed, underpriced second- and third-order market reactions after major industry news breaks?**

### Product/demo tagline
**When semiconductor news breaks, who gets hit next before the market fully realizes it?**

---

## Architecture

## 1. Data Ingestion Layer

This layer collects and normalizes all required data.

### Inputs

#### A. News / event data
We need semiconductor-relevant news items with:
- headline
- body text if available
- source/publisher
- published timestamp
- url or source identifier
- named entities if available
- tags if available

#### B. Market data
We need:
- daily OHLCV for target companies
- benchmark or sector ETF prices
- optional factor/industry benchmark returns
- optional index returns (SOXX, SMH, QQQ, SPY)

#### C. Ecosystem reference data
We need:
- company metadata
- segment classification
- market cap bucket
- role in ecosystem
- supplier/customer relationships where available
- manually curated strategic dependencies
- manually curated bottlenecks and thematic exposures

### Output datasets
- `news_events_raw`
- `market_prices_daily`
- `company_registry`
- `company_segment_map`
- `company_relationships`
- `theme_relationships`
- `benchmarks`

### Notes for coding agents
- Build the ingestion layer to be modular.
- Start with CSV / parquet support and clean interfaces.
- Prefer deterministic pipelines over brittle scraping where possible.
- It is acceptable to bootstrap with curated example datasets first, then expand.

---

## 2. Event Intelligence Layer

This layer converts raw text into structured events.

### Goal
Take a news item and map it to a machine-usable event object.

### Event object fields
At minimum:

- `event_id`
- `headline`
- `source`
- `published_at`
- `summary`
- `origin_companies`
- `mentioned_companies`
- `primary_segment`
- `secondary_segments`
- `event_type`
- `direction`
- `severity`
- `confidence`
- `reasoning`
- `market_relevance_score`

### Important distinction
This is **not** generic sentiment classification.
We care about **economic/industry meaning**, not just tone.

### Event taxonomy (initial)
Start with these categories:

- `export_controls_regulation`
- `ai_demand_hyperscaler_capex`
- `hbm_memory_pricing`
- `advanced_packaging_capacity`
- `foundry_capacity_or_utilization`
- `node_ramp_or_process_technology`
- `equipment_orders_or_capex`
- `supply_disruption`
- `earnings_or_guidance`
- `design_win_or_strategic_partnership`
- `inventory_correction_or_recovery`
- `pricing_pressure`
- `geopolitical_tension`
- `mna_or_strategic_restructuring`

### Direction field
Possible values:
- `positive`
- `negative`
- `mixed`
- `ambiguous`

Direction may apply differently to different downstream nodes, so event-level direction is only a starting point.

### Severity field
Possible values:
- `low`
- `medium`
- `high`
- `critical`

### Coding guidance
- Implement event extraction as a pipeline, not a single black-box step.
- Separate:
  1. entity extraction
  2. event type classification
  3. segment mapping
  4. severity estimation
  5. explanation generation
- Preserve intermediate outputs for debugging.
- Make it easy to swap between rule-based, LLM-assisted, and hybrid approaches.

---

## 3. Graph / Influence Modeling Layer

This is the core solution layer.

### Goal
Represent how impact can travel through the semiconductor ecosystem.

### Graph requirements
The graph should support both:
- company-to-company relationships
- company-to-theme / segment relationships

### Node categories
At minimum, support:
- `company`
- `segment`
- `technology`
- `demand_driver`
- `bottleneck`
- `region` (optional)
- `regulatory_theme` (optional)

### Edge categories
At minimum:
- `supplier_to`
- `customer_of`
- `competitor_to`
- `dependent_on`
- `benefits_from`
- `constrained_by`
- `exposed_to`
- `substitutes_for`
- `demand_flows_to`
- `bottleneck_for`

### Edge attributes
- `source_node`
- `target_node`
- `edge_type`
- `weight`
- `sign`
- `confidence`
- `evidence`
- `last_updated`

### Key modeling principle
The graph is a **knowledge-and-inference substrate**.
It is not just a pretty visual.

### Example propagation logic
If an event indicates:
- strong AI server demand
- increased HBM demand
- pressure on advanced packaging

Then propagation might travel through:
- hyperscaler capex -> GPU demand -> HBM suppliers -> advanced packaging -> substrates -> networking / power adjacencies

The engine should rank exposed names, not just traverse blindly.

### Coding guidance
- Use a graph-friendly internal representation.
- NetworkX is acceptable for initial iteration.
- A typed edge table is required even if a graph library is used.
- The edge table should remain a first-class data asset.
- Build deterministic scoring over the graph before optimizing.

---

## 4. Exposure Scoring Layer

This layer turns event + graph + company metadata into ranked company exposures.

### Goal
For a given event, estimate which companies are likely to be impacted and which may react with delay.

### Scoring concept
Each company should receive one or more scores such as:
- direct exposure score
- second-order exposure score
- third-order exposure score
- delayed-reaction score
- confidence score

### First-pass scoring factors

#### Structural exposure
How directly connected is the company to origin companies or impacted themes?

#### Segment exposure
Is the company in the affected segment or adjacent to it?

#### Historical similarity
How has the company reacted to similar prior events?

#### Lag tendency
Does this company tend to react on day 0 or later?

#### Obviousness penalty
If a name is the obvious headline beneficiary/loser, reduce the "hidden opportunity" character of the score.

### Suggested conceptual formula
This does not need to be final, but the coding agents should orient around something like:

`total_impact_score = structural_exposure + segment_exposure + historical_similarity + lag_profile - obviousness_penalty`

### Suggested output fields
For each `(event_id, ticker)` row:
- `event_id`
- `ticker`
- `impact_direction`
- `direct_exposure_score`
- `second_order_score`
- `third_order_score`
- `delayed_reaction_score`
- `total_rank_score`
- `confidence`
- `explanation`
- `top_paths` or `reason_codes`

### Important note
The goal is not only to score "who is affected," but also:
**who is likely underpriced and delayed.**

---

## 5. Lag Modeling Layer

This layer estimates timing.

### Goal
Predict when the market is likely to react.

### Why it matters
Our edge is not simply identifying impacted companies.
It is identifying companies that the market may price **later**.

### Lag windows
Start with:
- same day
- 1 trading day
- 3 trading days
- 5 trading days
- 10 trading days

### Lag profile ideas
A company may have a lag tendency based on:
- size / liquidity
- whether it is obvious vs non-obvious
- whether it is upstream or downstream
- whether it is a supplier, equipment vendor, packaging player, or memory name
- historical event response behavior

### Initial implementation guidance
Start simple:
- Use historical empirical lag tendencies by event type and company/segment class.
- Do not overbuild a complex time-series model too early.

---

## 6. Market Reaction / Evaluation Layer

This is the credibility layer.

### Goal
Measure whether our predicted names actually moved later in the predicted direction.

### Metrics to compute
For each predicted company around each event:
- raw return
- benchmark-adjusted return
- abnormal return
- abnormal volume
- rank among universe movers
- realized direction
- realized lag window

### Suggested evaluation windows
- T+0
- T+1
- T+3
- T+5
- T+10

### Universe
Start with a focused semiconductor universe, not the entire market.

### Main KPI
**Delayed Impact Hit Rate**

Definition:
Among top-N predicted non-obvious companies for an event, what fraction experience meaningful benchmark-adjusted movement in the expected direction within the predicted lag window?

### Other useful metrics
- Precision@3
- Precision@5
- Mean abnormal return for top predictions
- Event-category-specific hit rate
- Calibration by lag bucket
- Performance on origin names vs non-origin names
- Hidden-vs-obvious comparison

### Important product requirement
The app should be able to show historical examples:
- what the system predicted
- what actually happened
- whether the lagged move showed up

This is critical for trust and demo value.

---

## 7. Product Layer

We should ideally ship both an app and a simple API.

### App screens

#### A. Shock Feed
A list of recent semiconductor events with:
- headline
- timestamp
- category
- origin company
- severity
- quick summary

#### B. Event Detail View
When a user clicks an event, show:
- structured event summary
- origin company or companies
- key affected themes
- obvious first-order names
- likely second-order names
- likely third-order names
- expected lag
- confidence
- reasoning / exposure paths
- historical analogs

#### C. Company Exposure View
For a chosen company, show:
- which event types it is most exposed to
- its role in the ecosystem
- its typical lag behavior
- recent events likely to affect it

#### D. Backtest / Evidence View
Show:
- past event predictions
- realized market reactions
- scorecards
- event-category performance

### API endpoints
Suggested simple initial API:
- `POST /score_event`
- `GET /events`
- `GET /event/{event_id}`
- `GET /event/{event_id}/impacts`
- `GET /company/{ticker}/exposures`
- `GET /backtest/summary`

The API does not need to be elaborate. It exists to strengthen the end-to-end story.

---

## Zerve Usage Plan

We are allowed to build locally first and move into Zerve via GitHub.

### Intended workflow split

#### Local development
Use local development for:
- repo setup
- package management
- ingestion modules
- graph models
- scoring engine
- evaluation code
- unit tests
- data wrangling

#### Zerve
Use Zerve for:
- notebookized experimentation
- AI-assisted data analysis and iteration
- interactive exploration
- visual outputs
- backtest walkthroughs
- final app and/or API deployment
- submission-friendly demo environment

### Important implementation note
Do not treat Zerve as just a place to paste final code.
We want visible workflow there:
- ingestion
- event processing
- scoring
- backtest analysis
- deployed interface

---

## Recommended Repo Structure

```text
project-root/
├── README.md
├── AGENTS.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── data/
│   ├── raw/
│   ├── processed/
│   ├── reference/
│   └── external/
├── configs/
│   ├── taxonomy.yaml
│   ├── scoring_weights.yaml
│   ├── graph_schema.yaml
│   └── universe.yaml
├── docs/
│   ├── PROJECT_PLAN.md
│   ├── DATA_DICTIONARY.md
│   ├── EVENT_TAXONOMY.md
│   └── DEMO_SCRIPT.md
├── src/
│   ├── ingestion/
│   │   ├── news_ingest.py
│   │   ├── market_ingest.py
│   │   └── reference_ingest.py
│   ├── events/
│   │   ├── entity_extraction.py
│   │   ├── event_classifier.py
│   │   ├── event_mapper.py
│   │   └── event_models.py
│   ├── graph/
│   │   ├── build_graph.py
│   │   ├── edge_models.py
│   │   ├── node_models.py
│   │   └── propagation.py
│   ├── scoring/
│   │   ├── exposure_scoring.py
│   │   ├── lag_model.py
│   │   └── explanation_builder.py
│   ├── evaluation/
│   │   ├── abnormal_returns.py
│   │   ├── backtest.py
│   │   └── metrics.py
│   ├── api/
│   │   ├── main.py
│   │   └── schemas.py
│   ├── ui/
│   │   └── app.py
│   └── utils/
│       ├── logging.py
│       ├── dates.py
│       └── io.py
├── notebooks/
│   ├── 01_ingestion_and_universe.ipynb
│   ├── 02_event_intelligence.ipynb
│   ├── 03_graph_and_propagation.ipynb
│   ├── 04_scoring_and_lag.ipynb
│   ├── 05_backtest.ipynb
│   └── 06_demo_app_prep.ipynb
├── tests/
│   ├── test_event_classifier.py
│   ├── test_graph_build.py
│   ├── test_propagation.py
│   ├── test_scoring.py
│   └── test_backtest.py
└── outputs/
    ├── rankings/
    ├── charts/
    ├── backtests/
    └── demos/
```

---

## Data Model Suggestions

## A. Company registry schema

Suggested columns:
- `ticker`
- `company_name`
- `segment_primary`
- `segment_secondary`
- `ecosystem_role`
- `country`
- `market_cap_bucket`
- `is_origin_name_candidate`
- `notes`

## B. Relationship edge schema

Suggested columns:
- `edge_id`
- `source_type`
- `source_id`
- `target_type`
- `target_id`
- `edge_type`
- `weight`
- `sign`
- `confidence`
- `evidence`
- `last_updated`

## C. Event schema

Suggested columns:
- `event_id`
- `headline`
- `body`
- `source`
- `published_at`
- `event_type`
- `origin_companies`
- `mentioned_companies`
- `primary_segment`
- `secondary_segments`
- `direction`
- `severity`
- `confidence`
- `market_relevance_score`
- `summary`
- `reasoning`

## D. Event impact schema

Suggested columns:
- `event_id`
- `ticker`
- `impact_direction`
- `direct_exposure_score`
- `second_order_score`
- `third_order_score`
- `delayed_reaction_score`
- `total_rank_score`
- `confidence`
- `reason_codes`
- `top_paths`

## E. Evaluation schema

Suggested columns:
- `event_id`
- `ticker`
- `predicted_direction`
- `predicted_lag_bucket`
- `realized_return_t0`
- `realized_return_t1`
- `realized_return_t3`
- `realized_return_t5`
- `realized_return_t10`
- `abnormal_return_t1`
- `abnormal_return_t3`
- `abnormal_return_t5`
- `abnormal_return_t10`
- `hit_flag`
- `rank_realized_move`

---

## Initial Universe Recommendation

Do not start with hundreds of names.

Start with a curated semiconductor ecosystem universe of roughly **25-50 companies** across categories such as:
- foundries
- fabless designers
- memory
- equipment
- EDA
- packaging / test
- analog/power
- networking / connectivity
- substrate-adjacent if useful

This is enough for a strong MVP.

The universe can expand later.

---

## Initial Event Coverage Recommendation

For the hackathon, do not aim for every news event.

Start with a curated historical event set and a rolling live-like feed.

### Good initial event classes
- AI demand / hyperscaler capex
- HBM / memory pricing
- advanced packaging capacity
- export controls
- foundry capacity and utilization
- equipment spending
- earnings/guidance
- geopolitical disruption

These are rich enough to show propagation effects.

---

## MVP Definition

A strong MVP is:

1. A curated semiconductor company universe
2. A curated event taxonomy
3. An internal graph of company + theme relationships
4. Event parsing into structured events
5. Exposure scoring for second- and third-order effects
6. Lag-aware ranking of likely delayed movers
7. Backtest on a historical event set
8. App screen that shows event -> ranked impacted names -> why -> what happened later

If we can ship this, it is strong.

---

## What Not to Build First

Do **not** spend early time on:
- perfect real-time ingestion
- enterprise auth
- a complex distributed graph database
- minute-level trading strategies
- excessive UI polish before scoring works
- full causal inference claims
- general-purpose LLM agents everywhere

The core of the project is:
**event understanding + propagation + delayed-reaction scoring + evidence**

---

## Agent Instructions: Build Priorities

Coding agents should build in this order.

## Phase 1 - Foundation
- Create repo structure
- Create config files
- Define schemas / Pydantic models / dataclasses
- Create company registry
- Create relationship edge table
- Create event taxonomy config

## Phase 2 - Event Pipeline
- Ingest sample news/events
- Extract entities
- Map event type
- Produce normalized event records
- Store intermediate artifacts for inspection

## Phase 3 - Graph Layer
- Build graph from edge tables
- Support path tracing
- Support neighborhood queries
- Support weighted propagation logic

## Phase 4 - Scoring
- Implement exposure scoring
- Add direct/2nd/3rd-order decomposition
- Add delayed-reaction scoring
- Add explanation generation

## Phase 5 - Evaluation
- Compute benchmark-adjusted returns
- Backtest historical events
- Produce ranking metrics
- Save performance outputs for UI

## Phase 6 - Product
- Build simple API
- Build simple app
- Connect app to stored scored events
- Show evidence and reasoning

## Phase 7 - Zerve Packaging
- Move notebooks/workflows into Zerve
- Create notebook narrative
- Prepare demo-ready app/API
- Prepare submission screenshots / flow

---

## Agent Instructions: Behavioral Constraints

Coding agents should **not guess silently** when intent is clear from this document.

### The intended behavior is:
- Prefer explicit schemas
- Preserve explainability
- Keep intermediate tables inspectable
- Keep scoring modular
- Use configs for taxonomy and weights
- Favor deterministic implementations first
- Avoid overcomplication before MVP signal is visible

### If tradeoffs are needed:
Choose the option that improves:
1. interpretability
2. end-to-end completeness
3. demo readiness
4. historical validation

over theoretical sophistication.

---

## Explanation Requirements

This project must not output only raw scores.

Every high-ranked prediction should include an explanation such as:
- impacted theme
- relationship path
- why it is second-order vs third-order
- why the move may be delayed
- analogous past event if available

Explanations can be template-based initially.

Example reasoning:
- "Event indicates elevated AI server demand."
- "Company X is not the origin headline name but has strong exposure through HBM supply and advanced packaging dependence."
- "Historically this class of company reacts with a 1-5 day lag after similar demand shocks."
- "Ranked high due to strong thematic exposure and lower obviousness."

---

## Backtest Expectations

The project should support historical playback.

For each event, we want to be able to show:
- event headline
- event classification
- top predicted hidden names
- expected lag
- realized benchmark-adjusted reaction

This will likely be one of the strongest demo components.

---

## Demo Narrative

The demo should tell this story:

1. A major semiconductor headline arrives
2. Most people focus on the obvious ticker in the headline
3. Our system converts the headline into a structured event
4. It propagates that impact through the semiconductor ecosystem graph
5. It identifies less-obvious exposed names
6. It estimates which ones may move later
7. It shows the reasoning
8. It compares that with what historically happened

That is the product value.

---

## Deliverables We Want

At minimum:
- reusable Python codebase
- config-driven taxonomy
- graph-based scoring engine
- backtest notebook
- app or dashboard
- optional API
- Zerve notebook/project version
- short demo script

---

## Risks and Mitigations

### Risk: data availability complexity
Mitigation:
- start with curated datasets and a limited universe

### Risk: overbuilding the graph
Mitigation:
- keep graph schema simple and typed
- use edge tables as source of truth

### Risk: weak evaluation
Mitigation:
- focus on a smaller historical event set with stronger manual validation

### Risk: generic finance-tool feel
Mitigation:
- keep it deeply semiconductor-specific
- use ecosystem language and bottleneck logic

### Risk: too much magic / not enough explanation
Mitigation:
- require reason codes and path explanations for every prediction

---

## Success Criteria

We should consider the project successful if it can do the following convincingly:

1. Take a semiconductor news event
2. Normalize it into a structured event
3. Rank likely delayed second- and third-order impacted companies
4. Explain why those companies were selected
5. Show historical evidence that the system identifies non-obvious movers better than naive selection

### Stretch success
- app + API both working
- Zerve deployment complete
- historical examples are compelling and visual

---

## Suggested Next Files To Create

The coding agent should likely create these first:

- `README.md`
- `AGENTS.md`
- `configs/taxonomy.yaml`
- `configs/scoring_weights.yaml`
- `configs/graph_schema.yaml`
- `src/events/event_models.py`
- `src/graph/edge_models.py`
- `src/graph/build_graph.py`
- `src/scoring/exposure_scoring.py`
- `src/evaluation/backtest.py`
- `docs/DATA_DICTIONARY.md`
- `docs/EVENT_TAXONOMY.md`

---

## Final Intent Statement for Coding Agents

This project is intended to build a **semiconductor event propagation engine** that uses a **graph-based internal representation of ecosystem dependencies** to identify **delayed, underpriced second- and third-order market reactions** after major semiconductor industry news.

The question we are answering is:

**Which semiconductor companies are most likely to experience delayed, underpriced second- and third-order market reactions after major industry news breaks?**

The graph is part of the **solution**, not the wording of the question.

The priority is to deliver:
- a clear end-to-end pipeline,
- a working scoring engine,
- historical evaluation,
- and a demoable app/API in Zerve.

Avoid vague generalization.
Avoid silently changing the problem.
Stay semiconductor-specific.
Optimize for explainable, evidence-backed outputs.
