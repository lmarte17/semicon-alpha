from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from semicon_alpha.ingestion.eodhd import EODHDIngestionService
from semicon_alpha.ingestion.lithos import LithosIngestionService
from semicon_alpha.ingestion.reference import ReferenceDataService
from semicon_alpha.ingestion.source_enrichment import SourceEnrichmentService
from semicon_alpha.settings import Settings


def build_settings(storage_root: str | Path | None = None) -> Settings:
    kwargs: dict[str, Any] = {}
    if storage_root is not None:
        kwargs["SEMICON_ALPHA_STORAGE_ROOT"] = str(storage_root)
    settings = Settings(**kwargs)
    settings.ensure_directories()
    return settings


def run_news_workflow(
    *,
    settings: Settings | None = None,
    storage_root: str | Path | None = None,
    enrich_limit: int = 25,
    force_enrich: bool = False,
) -> dict[str, Any]:
    settings = settings or build_settings(storage_root=storage_root)
    lithos_service = LithosIngestionService(settings)
    enrichment_service = SourceEnrichmentService(settings)
    snapshot = lithos_service.run()
    enrichment = enrichment_service.run(limit=enrich_limit, force=force_enrich)
    summary = build_workspace_summary(settings)
    return {
        "snapshot": snapshot,
        "enrichment": enrichment,
        "summary": summary,
    }


def run_reference_workflow(
    *,
    settings: Settings | None = None,
    storage_root: str | Path | None = None,
    skip_exchange_symbols: bool = False,
) -> dict[str, Any]:
    settings = settings or build_settings(storage_root=storage_root)
    market_service = EODHDIngestionService(settings)
    reference_service = ReferenceDataService(settings, market_service)
    reference = reference_service.sync_reference_data(
        skip_exchange_symbols=skip_exchange_symbols
    )
    summary = build_workspace_summary(settings)
    return {"reference": reference, "summary": summary}


def run_market_workflow(
    *,
    start: str,
    end: str | None = None,
    settings: Settings | None = None,
    storage_root: str | Path | None = None,
) -> dict[str, Any]:
    settings = settings or build_settings(storage_root=storage_root)
    market_service = EODHDIngestionService(settings)
    market = market_service.sync_market_data(start=start, end=end)
    summary = build_workspace_summary(settings)
    return {"market": market, "summary": summary}


def load_processed_dataset(
    dataset_name: str,
    *,
    settings: Settings | None = None,
    storage_root: str | Path | None = None,
) -> pd.DataFrame:
    settings = settings or build_settings(storage_root=storage_root)
    path = settings.processed_dir / f"{dataset_name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Dataset does not exist: {path}")
    return pd.read_parquet(path)


def build_workspace_summary(
    settings: Settings | None = None,
    *,
    storage_root: str | Path | None = None,
) -> dict[str, Any]:
    settings = settings or build_settings(storage_root=storage_root)
    dataset_rows: list[dict[str, Any]] = []
    for path in sorted(settings.processed_dir.glob("*.parquet")):
        row_count = _safe_row_count(path)
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        dataset_rows.append(
            {
                "name": path.stem,
                "path": str(path),
                "rows": row_count,
                "modified_at": modified_at,
            }
        )
    return {
        "project_root": str(settings.project_root),
        "runtime_root": str(settings.runtime_root),
        "processed_dir": str(settings.processed_dir),
        "raw_dir": str(settings.raw_dir),
        "dataset_count": len(dataset_rows),
        "datasets": dataset_rows,
    }


def _safe_row_count(path: Path) -> int:
    try:
        return len(pd.read_parquet(path))
    except Exception:
        return -1
