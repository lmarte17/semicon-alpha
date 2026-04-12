# Zerve Setup

This repo is prepared to run both locally and inside Zerve.

## Goal

Keep the intelligence-engine code in Git, but let Zerve own:

- notebook orchestration
- secrets
- scheduled refreshes
- runtime storage
- app/API deployment

## Recommended Zerve Configuration

### 1. Environment

Install the package in the connected repo environment:

```bash
pip install -e .
```

If you want tests inside Zerve:

```bash
pip install -e ".[dev]"
```

### 2. Secrets

Set this secret in Zerve:

- `EODHD_API_KEY`

### 3. Runtime Storage

Set this environment variable in Zerve:

- `SEMICON_ALPHA_STORAGE_ROOT=runtime`

That makes all generated artifacts land in:

- `runtime/data/raw`
- `runtime/data/processed`
- `runtime/outputs`

instead of writing into the Git checkout.

## Notebook Execution Pattern

The notebook-friendly helpers live in:

- `src/semicon_alpha/workflows/zerve.py`

They are designed so Zerve cells can stay thin and readable.

### Bootstrap cell

```python
from semicon_alpha.workflows import build_settings, build_workspace_summary

settings = build_settings()
build_workspace_summary(settings)
```

### News ingestion cell

```python
from semicon_alpha.workflows import run_news_workflow

news_result = run_news_workflow(settings=settings, enrich_limit=25, force_enrich=False)
news_result
```

### Reference sync cell

```python
from semicon_alpha.workflows import run_reference_workflow

reference_result = run_reference_workflow(
    settings=settings,
    skip_exchange_symbols=False,
)
reference_result
```

### Market sync cell

```python
from semicon_alpha.workflows import run_market_workflow

market_result = run_market_workflow(
    settings=settings,
    start="2024-01-01",
)
market_result
```

### Dataset inspection cell

```python
from semicon_alpha.workflows import load_processed_dataset

news_articles = load_processed_dataset("news_articles_discovered", settings=settings)
company_registry = load_processed_dataset("company_registry", settings=settings)
market_prices = load_processed_dataset("market_prices_daily", settings=settings)
```

## Suggested Zerve Notebook Order

1. `00_bootstrap`
2. `01_news_ingestion`
3. `02_reference_sync`
4. `03_market_sync`
5. `04_workspace_summary`

Templates for those live in [notebooks/](../notebooks/README.md).

## Operational Notes

- Lithos is the discovery surface only. Exact article timestamps come from source-page enrichment.
- EODHD price history is live and working.
- EODHD fundamentals may return `403` depending on account permissions. The workflow now degrades gracefully and still produces the curated registry/theme/relationship tables.
- If you want deterministic demos, seed Zerve once with the current local processed outputs, then rerun the notebook live for freshness.

## What To Deploy Later

Once the event and scoring layers exist, Zerve should host:

- the notebook workflow for ingestion, event processing, scoring, and backtest walkthroughs
- a lightweight Streamlit app for event detail and evidence views
- optionally an API layer for scored events and company exposures
