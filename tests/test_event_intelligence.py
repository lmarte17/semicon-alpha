import json
import shutil
from pathlib import Path

import pandas as pd

from semicon_alpha.events import EventIntelligenceService
from semicon_alpha.settings import Settings


REPO_ROOT = Path(__file__).resolve().parents[1]


def _build_test_settings(tmp_path: Path) -> Settings:
    project_root = tmp_path / "project"
    configs_dir = project_root / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    for config_name in (
        "event_taxonomy.yaml",
        "relationship_edges.yaml",
        "theme_nodes.yaml",
        "universe.yaml",
    ):
        shutil.copy(REPO_ROOT / "configs" / config_name, configs_dir / config_name)
    settings = Settings(project_root=project_root, LLM_ENABLED=False)
    settings.ensure_directories()
    return settings


def test_event_intelligence_service_builds_structured_event_datasets(tmp_path):
    settings = _build_test_settings(tmp_path)

    enriched = pd.DataFrame(
        [
            {
                "article_id": "article1",
                "source_url": "https://news.example.com/packaging",
                "canonical_url": "https://news.example.com/packaging",
                "fetch_status": "success",
                "http_status": 200,
                "content_type": "text/html",
                "fetched_at_utc": "2026-04-12T00:00:00+00:00",
                "published_at_utc": "2026-04-11T14:00:00+00:00",
                "title": "Nvidia supplier TSMC says CoWoS capacity remains tight as HBM demand builds",
                "site_name": "Semicon Daily",
                "author": "Analyst Writer",
                "excerpt": "Advanced packaging constraints remain in focus.",
                "description": "AI infrastructure demand is keeping advanced packaging tight.",
                "body_text": (
                    "TSMC said CoWoS advanced packaging capacity remains tight as AI server "
                    "demand and HBM demand continue to build for Nvidia and AMD accelerators. "
                    "ASE and Amkor are expanding OSAT support."
                ),
                "raw_html_path": "raw1.html",
                "content_sha256": "abc123",
                "error_message": None,
            },
            {
                "article_id": "article2",
                "source_url": "https://news.example.com/export-controls",
                "canonical_url": "https://news.example.com/export-controls",
                "fetch_status": "success",
                "http_status": 200,
                "content_type": "text/html",
                "fetched_at_utc": "2026-04-12T01:00:00+00:00",
                "published_at_utc": "2026-04-11T18:00:00+00:00",
                "title": None,
                "site_name": None,
                "author": "Policy Desk",
                "excerpt": None,
                "description": "New rules limit shipments of advanced lithography tools.",
                "body_text": (
                    "The rules tighten export controls on advanced lithography systems to China "
                    "fabs, adding pressure on ASML and foundry customers such as TSMC and Intel."
                ),
                "raw_html_path": "raw2.html",
                "content_sha256": "def456",
                "error_message": None,
            },
        ]
    )
    enriched.to_parquet(settings.processed_dir / "news_articles_enriched.parquet", index=False)

    discovered = pd.DataFrame(
        [
            {
                "article_id": "article1",
                "title": "Discovery fallback not used",
                "summary_snippet": "Packaging article",
                "source_domain": "semicondaily.example.com",
            },
            {
                "article_id": "article2",
                "title": "New export controls hit ASML tool shipments to China fabs",
                "summary_snippet": "Advanced lithography tools face tighter restrictions.",
                "source_domain": "policywire.example.com",
            },
        ]
    )
    discovered.to_parquet(settings.processed_dir / "news_articles_discovered.parquet", index=False)

    service = EventIntelligenceService(settings)
    result = service.run()

    assert result["event_count"] == 2
    assert result["entity_count"] >= 6
    assert result["classification_count"] >= 2
    assert result["theme_count"] >= 2

    events = pd.read_parquet(settings.processed_dir / "news_events_structured.parquet")
    assert set(events["article_id"]) == {"article1", "article2"}

    packaging_event = events.loc[events["article_id"] == "article1"].iloc[0]
    assert packaging_event["event_type"] == "advanced_packaging_capacity"
    assert packaging_event["direction"] == "negative"
    assert packaging_event["severity"] in {"high", "critical"}
    assert {"NVDA", "TSM"}.issubset(set(json.loads(packaging_event["origin_companies"])))
    assert "Advanced Packaging Capacity".lower() not in packaging_event["headline"].lower()

    export_event = events.loc[events["article_id"] == "article2"].iloc[0]
    assert export_event["headline"] == "New export controls hit ASML tool shipments to China fabs"
    assert export_event["source"] == "policywire.example.com"
    assert export_event["event_type"] == "export_controls_regulation"
    assert export_event["direction"] == "negative"

    entities = pd.read_parquet(settings.processed_dir / "news_event_entities.parquet")
    export_tickers = set(entities.loc[entities["article_id"] == "article2", "ticker"])
    assert {"ASML", "TSM", "INTC"}.issubset(export_tickers)

    themes = pd.read_parquet(settings.processed_dir / "news_event_themes.parquet")
    packaging_themes = set(themes.loc[themes["article_id"] == "article1", "theme_id"])
    assert "theme:advanced_packaging" in packaging_themes
    assert "theme:hbm_demand" in packaging_themes

    classifications = pd.read_parquet(settings.processed_dir / "news_event_classifications.parquet")
    selected_export = classifications[
        (classifications["article_id"] == "article2") & (classifications["is_selected"])
    ].iloc[0]
    assert selected_export["event_type"] == "export_controls_regulation"
