# LLM Intelligence Implementation Plan

## Purpose

This document turns the current LLM review into an implementation sequence that fits the existing Semicon Alpha architecture.

The goal is not to replace the deterministic engine. The goal is to add model-based judgment where the current system is weakest:

- article relevance triage
- structured event review and extraction
- semantic retrieval
- grounded analyst-facing synthesis
- ontology and relationship proposal workflows
- evaluation and miss-diagnosis sidecars

The guiding principle is:

- keep the world model deterministic by default
- add LLMs as schema-bound sidecars
- preserve provenance and auditability
- avoid agent loops for now
- build in waves so each stage can ship independently

## Scope Boundary

This plan assumes the current system already exists and remains the source of truth for:

- ingestion and enrichment
- deterministic Event Intelligence
- graph construction and propagation
- lag modeling
- exposure scoring
- market-reaction evaluation
- terminal/API workflows

This plan does **not** assume an agentic orchestration layer.

Out of scope for this phase:

- autonomous agents
- model-directed graph traversal
- model-only ranking logic
- replacing deterministic score math with opaque generation

## Runtime Assumptions

### Models

Use these models as the default assumptions for implementation:

- default high-volume model: `gemini-3.1-flash-lite-preview`
- default deep-reasoning fallback: `gemini-3.1-pro-preview`

### Credentials

- load the Gemini key from `.env` as `GEMINI_API_KEY`

### Model routing policy

Use `gemini-3.1-flash-lite-preview` for:

- article triage
- schema-bound extraction
- embeddings-related enrichment prompts if needed
- report/citation synthesis when the evidence set is straightforward
- evaluation miss classification

Use `gemini-3.1-pro-preview` only for:

- disagreement resolution between deterministic and LLM extraction
- hard entity / relationship disambiguation
- analyst-triggered deep explanations
- difficult scenario / thesis synthesis over larger evidence sets

### Integration policy

- every LLM call must be schema-bound
- every LLM output must be versioned
- every LLM output must carry confidence and abstain behavior
- every LLM-assisted decision must preserve the underlying source evidence

## Why LLMs Fit This Repo

The current system is strongest where it is structured and weakest where it requires semantic judgment.

The main fit points are:

1. deterministic event extraction is currently keyword and alias heavy
2. retrieval currently uses a local pseudo-embedding approach
3. copilot and reports are currently grounded but template-based
4. graph quality is constrained by curated ontology breadth
5. evaluation can tell whether the system missed, but not why at a semantic level

The main non-fit points are:

- graph path scoring
- propagation hop logic
- exposure rank arithmetic
- lag bucket calculation

Those should stay deterministic.

## Architecture Principles

### 1. Deterministic-first

The deterministic engine remains primary. LLMs produce sidecar artifacts that can:

- gate
- enrich
- review
- propose
- explain

They should not silently override the engine.

### 2. Structured outputs only

Every model call should target a strict schema. No freeform parsing in the data pipeline.

### 3. Evidence-preserving

Every output should retain:

- article IDs
- source URLs
- evidence snippets or referenced spans
- deterministic context used for the prompt
- prompt and schema version

### 4. Abstention over hallucination

Every schema should include:

- `confidence`
- `uncertainty_flags`
- `abstain`
- `needs_review`

### 5. Sidecar datasets, not hidden state

All model outputs should land in explicit datasets rather than transient runtime objects.

### 6. Incremental rollout

Each wave should improve a specific product or pipeline weakness and be independently reversible.

## Shared Foundation Work

Build this once before any wave depends on it.

### Platform deliverables

- `src/semicon_alpha/llm/client.py`
- `src/semicon_alpha/llm/config.py`
- `src/semicon_alpha/llm/schemas.py`
- `src/semicon_alpha/llm/prompts/`
- `src/semicon_alpha/llm/router.py`
- `src/semicon_alpha/llm/logging.py`
- `src/semicon_alpha/llm/batch.py`

### Config deliverables

- `GEMINI_API_KEY`
- `GEMINI_FLASH_MODEL=gemini-3.1-flash-lite-preview`
- `GEMINI_PRO_MODEL=gemini-3.1-pro-preview`
- `LLM_ENABLED=true`
- `LLM_MIN_CONFIDENCE_*` thresholds by workflow

### Shared operational features

- retries with exponential backoff
- timeout handling
- structured output validation
- cost and token logging
- prompt versioning
- schema versioning
- cached prefix/context support where helpful
- batch mode for backfills
- online mode for interactive UX

### Shared record models

Add first-class records for:

- `llm_job_runs`
- `article_llm_triage`
- `event_llm_reviews`
- `event_llm_fusion_decisions`
- `retrieval_embeddings`
- `graph_relation_candidates_llm`
- `impact_llm_reviews`
- `evaluation_miss_diagnoses`
- `copilot_llm_responses`
- `report_llm_generations`

### Shared dataset rules

Each LLM-derived record should include:

- stable ID
- source object IDs
- model name
- prompt version
- schema version
- created timestamp
- confidence
- abstain flag
- review flag
- raw reasoning summary
- serialized structured payload

### Rollout gate

Do not start Wave 1 until:

- a single Gemini client wrapper exists
- schemas validate locally
- batch and online execution are both proven
- job logging exists

## Wave 0: LLM Platform Foundation

### Goal

Create the shared LLM runtime layer and the audit trail required for every downstream wave.

### Deliverables

- Gemini API client wrapper
- model router for Flash Lite vs Pro
- prompt registry
- structured output schemas
- llm job log dataset
- CLI smoke command such as `semicon-alpha llm-check`

### Implementation notes

- keep the client generic and stateless
- isolate provider-specific code under `src/semicon_alpha/llm/`
- make schemas importable by both batch jobs and API services
- include a thin helper for prompt rendering with explicit prompt versions

### Testing

- unit tests for schema validation
- tests for retry / timeout behavior
- tests for config loading from `.env`
- mocked Gemini client tests for both models

### Exit criteria

- one successful structured call through Flash Lite
- one successful structured call through Pro
- job traces persist to processed data or a local audit log location

## Wave 1: Article Relevance Triage

### Goal

Stop low-value or non-semiconductor Lithos articles from flowing into Event Intelligence.

### Why first

This addresses the most obvious live-system weakness: noisy upstream article flow.

### Integration point

Insert after:

- `news_articles_discovered.parquet`
- `news_articles_enriched.parquet`

and before:

- `event-sync`

### New datasets

- `data/processed/article_llm_triage.parquet`
- optional `data/processed/article_triage_queue.parquet`

### Suggested schema

- `article_id`
- `headline`
- `source_url`
- `source`
- `relevance_label`
- `is_semiconductor_relevant`
- `is_event_worthy`
- `article_type`
- `primary_subjects`
- `mentioned_companies`
- `mentioned_technologies`
- `mentioned_countries`
- `confidence`
- `abstain`
- `needs_review`
- `rejection_reason`
- `reasoning_summary`
- `model_name`
- `prompt_version`
- `processed_at_utc`

### Prompt task

Given article metadata and text, classify whether the article:

- is materially semiconductor-related
- contains a concrete event rather than background commentary
- should continue to event extraction
- should be suppressed from propagation

### Decision policy

- pass directly if deterministic rules and LLM agree it is relevant
- suppress directly if both agree it is irrelevant
- send to review / fallback deterministic path if disagreement is large

### CLI/API additions

- `semicon-alpha article-triage`
- optional `semicon-alpha article-triage --backfill`

### Terminal/product use

- expose triage status in evidence panes for debugging
- show filtered vs included counts on an admin/ops page later

### Risks

- over-filtering high-value edge cases
- model drift on preview models
- source-specific bias

### Mitigations

- keep deterministic fallback for high-priority sources
- sample rejected articles for manual QA
- log source-domain rejection rates

### Exit criteria

- measurable reduction in off-topic event creation
- no meaningful drop in known-good semiconductor article coverage

## Wave 2: Event Review And Structured Extraction

### Goal

Upgrade event extraction from purely deterministic heuristics to a deterministic-plus-LLM fusion model.

### Why second

Once irrelevant articles are filtered, the next problem is event quality: correct event type, direction, theme, entity, and severity assignment.

### Integration point

Hook into the current `EventIntelligenceService` after deterministic candidate generation and before writing final structured event outputs.

### New datasets

- `data/processed/event_llm_reviews.parquet`
- `data/processed/event_llm_entities.parquet`
- `data/processed/event_llm_themes.parquet`
- `data/processed/event_llm_fusion_decisions.parquet`

### Suggested schema

For `event_llm_reviews`:

- `event_id`
- `article_id`
- `deterministic_event_type`
- `llm_event_type`
- `deterministic_direction`
- `llm_direction`
- `deterministic_severity`
- `llm_severity`
- `llm_summary`
- `llm_reasoning_summary`
- `confidence`
- `abstain`
- `needs_review`
- `disagreement_flags`
- `model_name`
- `prompt_version`
- `processed_at_utc`

For sidecar entity/theme tables:

- extracted item IDs and names
- role labels such as `origin`, `affected`, `regulator`, `technology`, `facility`
- evidence snippets or quoted support
- confidence

### Fusion policy

The LLM should not directly overwrite the deterministic event.

Use a fusion layer that:

- accepts deterministic output when confidence is high and LLM agrees
- upgrades deterministic output when LLM confidence is high and deterministic confidence is weak
- flags disagreement when event type, direction, or origin entity conflict materially
- optionally escalates difficult cases to Pro

### Extraction targets

- event taxonomy selection
- origin vs affected company distinction
- non-company entity extraction
- theme mapping
- event time horizon hints
- contradiction / uncertainty markers
- evidence span selection

### Changes to current outputs

Keep existing outputs intact:

- `news_event_entities.parquet`
- `news_event_classifications.parquet`
- `news_event_themes.parquet`
- `news_events_structured.parquet`

Add fields where needed rather than replacing the tables outright.

Recommended additions to `StructuredEventRecord`:

- `extraction_method`
- `llm_review_status`
- `evidence_spans`
- `uncertainty_flags`
- `review_notes`

### Model routing

- Flash Lite for first-pass review
- Pro only when:
  - deterministic and Flash Lite disagree on core fields
  - confidence is low on both sides
  - a monitored source/domain has repeated extraction errors

### Exit criteria

- improved event relevance and classification precision
- fewer obviously wrong theme/entity assignments
- explicit disagreement logging exists

## Wave 3: Gemini Embeddings And Retrieval Upgrade

### Goal

Replace the current pseudo-semantic retrieval layer with real model-backed embeddings.

### Why third

This unlocks better search, analog retrieval, copilot grounding, and later report quality.

### Integration point

Upgrade the current retrieval layer rather than introducing a separate search stack.

### New datasets

- `data/processed/retrieval_embeddings.parquet`
- optional `data/processed/retrieval_chunks.parquet`

### Changes to existing outputs

Enhance or rebuild:

- `data/processed/retrieval_index.parquet`

### Data model additions

- `item_id`
- `search_category`
- `embedding_model`
- `embedding_vector`
- `embedding_version`
- `semantic_text`
- `chunk_id` if chunking documents
- `chunk_rank`
- `updated_at_utc`

### Retrieval scope

Embed:

- entities
- events
- themes
- enriched documents
- selected graph relation evidence
- reports
- scenario and thesis text later

### Service work

- replace local hash-vector generation
- support chunking for long document bodies
- support hybrid lexical + embedding reranking
- add similarity search for:
  - events
  - documents
  - entity context

### Product outcomes

- better global search
- better historical analog retrieval
- better contradiction / support retrieval for scenarios and theses
- better evidence selection for copilot

### Exit criteria

- search precision materially improves on event/entity/document lookups
- analog retrieval becomes meaningfully more relevant than current event-type matching

## Wave 4: Grounded LLM Synthesis For Copilot And Reports

### Goal

Upgrade the analyst-facing language layer while keeping all retrieval and reasoning grounded in existing services.

### Why fourth

By this point the retrieval base and event quality should be strong enough to justify higher-level synthesis.

### Integration points

- `CopilotService`
- `ReportService`
- selected event and entity workspace summaries

### New datasets

- `data/processed/copilot_llm_responses.parquet`
- `data/processed/report_llm_generations.parquet`

### Response contract

Every response should separate:

- observations
- inferences
- uncertainties
- next checks
- citations used

### Copilot design

Keep server-side routing deterministic:

- resolve scope
- fetch evidence bundle
- select the prompt template
- call Gemini once
- validate schema

Do not let the model decide what tools to call on its own in this phase.

### Report generation upgrades

Use Gemini to synthesize:

- `event_impact_brief`
- `weekly_thematic_brief`
- `entity_comparison_brief`
- `scenario_memo`
- `thesis_change_report`

but require every report to be built from a bounded payload created by deterministic services.

### Prompt constraints

- cite only provided evidence
- distinguish observed facts from inferred impacts
- surface disagreements and missing evidence explicitly
- no unsupported claims

### Model routing

- Flash Lite for most copilot answers and standard reports
- Pro for:
  - long scenario/thesis reports
  - large evidence bundles
  - analyst-requested deep comparisons

### Exit criteria

- responses become more natural without losing grounding
- citations remain correct
- hallucination rate is operationally acceptable

## Wave 5: Graph And Ontology Candidate Generation

### Goal

Use LLMs to propose graph improvements without allowing them to mutate the production graph directly.

### Why fifth

Once event extraction and retrieval improve, the next bottleneck becomes ontology coverage and missing relationships.

### Integration points

- article/event review outputs
- graph and ontology datasets
- admin/review workflows

### New datasets

- `data/processed/graph_relation_candidates_llm.parquet`
- `data/processed/ontology_node_candidates_llm.parquet`
- `data/processed/relation_review_queue.parquet`

### Candidate types

- supplier/customer relation proposals
- regulator-to-company relation proposals
- country/facility exposure proposals
- material / capability / technology dependency proposals
- alias expansions for entities

### Required fields

- candidate ID
- source event/article IDs
- proposed source and target nodes
- proposed edge type
- proposed sign
- evidence snippets
- confidence
- novelty score
- review status
- accepted/rejected timestamps

### Review policy

No auto-merge into `graph_edges.parquet`.

Use a human-review or rule-validated acceptance flow:

- accept
- reject
- defer

Accepted items can then flow into curated relationship config or a managed derived-edge layer.

### Product outcomes

- broader ontology coverage
- fewer missing-path cases
- better scenario and thesis support over time

### Exit criteria

- relation proposals are useful enough to reduce manual curation burden
- accepted candidate precision is operationally acceptable

## Wave 6: Impact, Lag, And Evaluation Sidecars

### Goal

Add semantic diagnosis and explanation to the deterministic rank/evaluation layers.

### Why sixth

This should come only after upstream quality improves, otherwise model explanations will rationalize noisy inputs.

### Integration points

- `event_lag_predictions.parquet`
- `event_impact_scores.parquet`
- `event_market_reactions.parquet`
- `evaluation_summary.parquet`

### New datasets

- `data/processed/impact_llm_reviews.parquet`
- `data/processed/evaluation_miss_diagnoses.parquet`
- optional `data/processed/analog_explanations_llm.parquet`

### Use cases

#### Impact review

For each ranked event-company pair, generate:

- mechanism summary
- why the exposure is non-obvious or obvious
- why the lag may be delayed
- key supporting paths
- counterarguments

#### Miss diagnosis

For evaluated misses or false positives, classify causes such as:

- bad article triage
- wrong event type
- wrong origin entity
- missing graph edge
- bad lag estimate
- bad ranking despite correct graph
- non-event / macro noise

#### Analog explanation

For retrieved analogs, explain:

- why they are similar
- where the analogy breaks
- what should be monitored differently this time

### Policy

These outputs should not overwrite numeric scores.

They should augment:

- analyst workspaces
- report generation
- evaluation dashboards
- future model and rules tuning

### Exit criteria

- analysts can inspect misses more quickly
- the system gains a clear tuning loop from miss categorization

## Wave 7: Operationalization, QA, And Governance

### Goal

Make the LLM layer maintainable in production instead of becoming an opaque, expensive side system.

### Why last

This wave hardens all previous work and should be built as capabilities mature.

### Deliverables

- per-wave dashboarding
- cost tracking by workflow
- latency tracking by workflow
- model failure alerts
- disagreement-rate monitoring
- rejection-rate monitoring
- human review utilities
- prompt regression suite
- gold-label evaluation sets

### QA slices

Create evaluation sets for:

- article triage
- event extraction
- analog retrieval
- copilot citation correctness
- miss diagnosis
- relation proposal quality

### Governance rules

- keep prompt changes versioned
- log model name on every output
- block silent schema drift
- retain a deterministic fallback for every critical pipeline stage
- make preview-model assumptions easy to swap later

## Recommended File And Module Layout

### New modules

- `src/semicon_alpha/llm/`
- `src/semicon_alpha/llm/prompts/`
- `src/semicon_alpha/llm/workflows/triage.py`
- `src/semicon_alpha/llm/workflows/event_review.py`
- `src/semicon_alpha/llm/workflows/retrieval.py`
- `src/semicon_alpha/llm/workflows/copilot.py`
- `src/semicon_alpha/llm/workflows/reports.py`
- `src/semicon_alpha/llm/workflows/graph_candidates.py`
- `src/semicon_alpha/llm/workflows/evaluation.py`

### Existing areas likely to change

- `src/semicon_alpha/events/pipeline.py`
- `src/semicon_alpha/retrieval/index.py`
- `src/semicon_alpha/services/search.py`
- `src/semicon_alpha/services/copilot.py`
- `src/semicon_alpha/services/reports.py`
- `src/semicon_alpha/services/events.py`
- `src/semicon_alpha/services/entities.py`
- `src/semicon_alpha/models/records.py`
- `src/semicon_alpha/cli.py`
- `src/semicon_alpha/settings.py`

## Cross-Cutting Implementation Rules

### Prompt design

- one task per prompt
- schema-first responses
- explicit abstain instructions
- explicit evidence-only instructions
- prompt versions stored in code, not ad hoc strings

### Data retention

- keep structured outputs in parquet
- avoid storing excessive raw prompt bodies in processed datasets
- if raw request/response logs are needed, store them in a separate audit path

### Fallback behavior

If the LLM layer fails:

- ingestion should continue
- deterministic event extraction should still run
- terminal search should still work lexically
- reports should still fall back to template generation

### Cost control

- use Batch API for backfills
- use Flash Lite first
- use Pro only on escalation paths
- cache reusable context
- skip reprocessing unchanged documents

### Latency control

- separate online and offline workflows
- do not block interactive pages on long-running model review jobs
- surface the latest available reviewed artifact with status metadata

## Recommended Execution Order

Build in this order:

1. Wave 0 foundation
2. Wave 1 article triage
3. Wave 2 event review and extraction
4. Wave 3 embeddings and retrieval
5. Wave 4 grounded copilot and reports
6. Wave 5 graph and ontology candidate generation
7. Wave 6 scoring and evaluation sidecars
8. Wave 7 operational hardening

## Immediate First Milestone

The best first implementation milestone is:

1. build the Gemini client foundation
2. add `article-triage`
3. write `article_llm_triage.parquet`
4. gate `event-sync` on triage status
5. add QA metrics for accepted vs rejected articles

That gives the fastest quality improvement with the least architectural risk.

## Success Definition

This LLM program is successful if it produces the following outcome:

- fewer bad articles become events
- event extraction becomes materially more correct
- search and analog retrieval become meaningfully better
- copilot and reports become more useful without losing grounding
- graph coverage improves through reviewed proposals
- misses become diagnosable rather than mysterious
- the deterministic engine remains explainable and primary
