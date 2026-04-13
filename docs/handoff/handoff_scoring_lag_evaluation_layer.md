# Exposure Scoring / Lag Modeling / Market Evaluation Handoff

## Purpose

This document captures the current end-state of the Phase 1 analytical stack above the graph layer:

- lag modeling
- event-company exposure scoring
- realized market-reaction evaluation

The goal is to let a new session continue from ranked impacts and evidence outputs without having to rediscover score components, lag semantics, evaluation windows, or output datasets.

## What Exists

The repo now contains a working scoring-and-evaluation stack with these major components:

1. Config-driven lag model
   - Uses `configs/scoring_rules.yaml`
   - Produces:
     - `event_lag_predictions.parquet`
     - optional empirical `lag_profiles.parquet`
   - Lag predictions use:
     - graph hop depth
     - direct / second-order / third-order exposure mix
     - company market-cap bucket
     - ecosystem role
     - non-obviousness heuristics
     - optional empirical feedback from earlier evaluated events

2. Exposure scoring layer
   - Produces `event_impact_scores.parquet`
   - Each `(event_id, ticker)` row now includes:
     - direct / second / third-order scores
     - structural exposure score
     - segment exposure score
     - historical similarity score
     - delayed reaction score
     - obviousness penalty
     - total rank score
     - confidence
     - predicted lag bucket
     - explanation and path payloads

3. Market-reaction evaluation layer
   - Produces:
     - `event_market_reactions.parquet`
     - `evaluation_summary.parquet`
   - Computes:
     - raw returns across T+0 / T+1 / T+3 / T+5 / T+10
     - benchmark-adjusted returns
     - abnormal volume
     - realized lag bucket
     - hit flag
     - realized-move rank
     - top-level summary KPIs

4. CLI integration
   - Adds:
     - `semicon-alpha lag-sync`
     - `semicon-alpha score-sync`
     - `semicon-alpha evaluate-sync`

## Storage Model

The layer follows the same parquet-first pattern used elsewhere in the repo:

- normalized analytical datasets live in `data/processed/`
- DuckDB exposes these parquet outputs as views in `data/semicon_alpha.duckdb`

The scoring/evaluation stack is intentionally inspectable:

- lag predictions are explicit
- ranked impacts are explicit
- realized market outcomes are explicit
- summary metrics are explicit

## Current Modeling Decisions

### Lag modeling

- Lag buckets are:
  - `same_day`
  - `1d`
  - `3d`
  - `5d`
  - `10d`
- The current model is deterministic, not learned.
- First pass uses heuristics tied to path depth, directness, company size, and ecosystem role.
- If earlier evaluation rows exist, the lag model blends in empirical feedback for:
  - `ticker + event_type`
  - `segment_primary + event_type`
  - `ecosystem_role + event_type`

### Exposure scoring

- The total rank score is additive and explainable.
- Current components are:
  - structural exposure
  - segment exposure
  - historical similarity
  - lag profile
  - obviousness penalty
- `is_non_obvious` is intentionally not just a cap-size flag.
- It currently requires:
  - not being an origin company
  - not being a directly mentioned company
  - and either deeper path depth or limited direct exposure

### Historical similarity

- Historical similarity is currently evaluation-driven.
- It only contributes when prior evaluated rows exist before the current event date.
- Supported fallback scopes are:
  - `ticker + event_type`
  - `segment_primary + event_type`
  - `ecosystem_role + event_type`

### Market evaluation

- Evaluation currently uses trading-day windows, not calendar-day windows.
- Benchmark-adjusted return is treated as the abnormal-return signal.
- The default benchmark comes from `configs/scoring_rules.yaml` and currently points to `SOXX`.
- `hit_flag` is based on whether the predicted direction showed a meaningful benchmark-adjusted move by the predicted lag bucket.

## Core Output Datasets

The scoring/evaluation stack now produces:

- `lag_profiles.parquet`
- `event_lag_predictions.parquet`
- `event_impact_scores.parquet`
- `event_market_reactions.parquet`
- `evaluation_summary.parquet`

## Verification Status

Verified locally:

- new scoring/evaluation integration tests pass
- full test suite passes
- `lag-sync` runs against the current local parquet data
- `score-sync` runs against the current local parquet data
- `evaluate-sync` runs against the current local parquet data
- new processed datasets are written and exposed to DuckDB

## Important Caveats

- `lag_profiles.parquet` can legitimately be empty when no prior evaluated events exist.
- Historical similarity is therefore zero on a cold start.
- The market-evaluation layer currently assumes the event anchor is the first trading date on or after the event publish date.
- This is good enough for Phase 1, but later versions may want a stricter market-hours model.
- Summary metrics are still lightweight and should be treated as MVP scorecards, not final research metrics.

## Recommended Next Step

The next highest-value work is one of:

1. historical analog retrieval
   - attach past similar events directly to each scored event

2. product-layer event detail surfaces
   - expose `event_impact_scores` and `event_market_reactions` in API/UI endpoints

3. score calibration and tuning
   - tune weights and hit thresholds using a larger historical event set

The current repo now has the full Phase 1 analytical chain:

- event intelligence
- graph propagation
- lag prediction
- ranked impact scoring
- realized market evaluation

That is enough to support a credible demo and to begin building the product layer on top.
