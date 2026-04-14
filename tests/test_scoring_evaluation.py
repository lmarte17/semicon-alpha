import json
import shutil
from pathlib import Path

import pandas as pd
import yaml

from semicon_alpha.evaluation import MarketEvaluationService
from semicon_alpha.graph import GraphBuildService, GraphPropagationService
from semicon_alpha.scoring import ExposureScoringService, LagModelingService
from semicon_alpha.settings import Settings


REPO_ROOT = Path(__file__).resolve().parents[1]


def _build_test_settings(tmp_path: Path) -> Settings:
    project_root = tmp_path / "project"
    configs_dir = project_root / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    for config_name in (
        "benchmarks.yaml",
        "graph_schema.yaml",
        "ontology_nodes.yaml",
        "relationship_edges.yaml",
        "scoring_rules.yaml",
        "theme_nodes.yaml",
        "universe.yaml",
    ):
        shutil.copy(REPO_ROOT / "configs" / config_name, configs_dir / config_name)
    settings = Settings(project_root=project_root)
    settings.ensure_directories()
    return settings


def _write_reference_parquets(settings: Settings) -> None:
    universe_payload = yaml.safe_load((settings.configs_dir / "universe.yaml").read_text(encoding="utf-8"))
    relationship_payload = yaml.safe_load(
        (settings.configs_dir / "relationship_edges.yaml").read_text(encoding="utf-8")
    )
    ontology_payload = yaml.safe_load((settings.configs_dir / "ontology_nodes.yaml").read_text(encoding="utf-8"))
    theme_payload = yaml.safe_load((settings.configs_dir / "theme_nodes.yaml").read_text(encoding="utf-8"))

    company_rows = []
    for company in universe_payload["companies"]:
        company_rows.append(
            {
                "entity_id": f"company:{company['ticker']}",
                "ticker": company["ticker"],
                "eodhd_symbol": company["eodhd_symbol"],
                "company_name": company["company_name"],
                "exchange": company["exchange"],
                "country": company["country"],
                "segment_primary": company["segment_primary"],
                "segment_secondary": json.dumps(company["segment_secondary"]),
                "ecosystem_role": company["ecosystem_role"],
                "market_cap_bucket": company["market_cap_bucket"],
                "is_origin_name_candidate": company["is_origin_name_candidate"],
                "notes": company.get("notes"),
                "sector": None,
                "industry": None,
                "description": None,
                "website": None,
                "isin": None,
                "lei": None,
                "cik": None,
                "reference_last_updated": "2026-04-12T00:00:00+00:00",
            }
        )
    pd.DataFrame(company_rows).to_parquet(settings.processed_dir / "company_registry.parquet", index=False)
    pd.DataFrame(theme_payload["themes"]).to_parquet(settings.processed_dir / "theme_nodes.parquet", index=False)
    pd.DataFrame(ontology_payload["nodes"]).to_parquet(settings.processed_dir / "ontology_nodes.parquet", index=False)

    company_edges = [
        edge
        for edge in relationship_payload["edges"]
        if edge["source_type"] == "company" and edge["target_type"] == "company"
    ]
    theme_edges = [
        edge
        for edge in relationship_payload["edges"]
        if "theme" in {edge["source_type"], edge["target_type"]}
    ]
    ontology_edges = [
        edge
        for edge in relationship_payload["edges"]
        if not (
            edge["source_type"] == "company" and edge["target_type"] == "company"
        )
        and "theme" not in {edge["source_type"], edge["target_type"]}
    ]
    pd.DataFrame(company_edges).to_parquet(
        settings.processed_dir / "company_relationships.parquet", index=False
    )
    pd.DataFrame(theme_edges).to_parquet(
        settings.processed_dir / "theme_relationships.parquet", index=False
    )
    pd.DataFrame(ontology_edges).to_parquet(
        settings.processed_dir / "ontology_relationships.parquet", index=False
    )


def _write_events(settings: Settings, events: list[dict], themes: list[dict]) -> None:
    pd.DataFrame(events).to_parquet(settings.processed_dir / "news_events_structured.parquet", index=False)
    pd.DataFrame(themes).to_parquet(settings.processed_dir / "news_event_themes.parquet", index=False)


def _write_market_prices(settings: Settings) -> None:
    company_registry = pd.read_parquet(settings.processed_dir / "company_registry.parquet")
    trade_dates = pd.bdate_range("2026-04-01", periods=30).date

    company_rows = []
    benchmark_rows = []
    for ticker in company_registry["ticker"].tolist():
        base_price = 100.0
        for index, trade_date in enumerate(trade_dates):
            price = base_price + (index * 0.20)
            volume = 1_000_000 + (index * 1_000)

            if ticker == "NVDA":
                if index >= 1:
                    price += 4.0
                    volume += 400_000
                if index >= 13:
                    price += 4.0
                    volume += 450_000
            if ticker == "AVGO":
                if index >= 4:
                    price += 3.0
                    volume += 300_000
                if index >= 16:
                    price += 2.5
                    volume += 250_000
            if ticker == "TSM":
                if index >= 6:
                    price += 5.0
                    volume += 350_000
                if index >= 18:
                    price += 4.5
                    volume += 325_000
            if ticker == "AMD" and index >= 3:
                price += 1.5
                volume += 150_000

            company_rows.append(
                {
                    "entity_id": f"company:{ticker}",
                    "ticker": ticker,
                    "eodhd_symbol": f"{ticker}.US",
                    "source_table": "company_prices",
                    "trade_date": trade_date.isoformat(),
                    "open": round(price - 0.5, 4),
                    "high": round(price + 0.5, 4),
                    "low": round(price - 1.0, 4),
                    "close": round(price, 4),
                    "adjusted_close": round(price, 4),
                    "volume": float(volume),
                    "fetched_at_utc": "2026-04-12T00:00:00+00:00",
                }
            )

    for benchmark_ticker in ("SOXX", "SMH"):
        for index, trade_date in enumerate(trade_dates):
            price = 100.0 + (index * 0.10)
            if index >= 1:
                price += 0.8
            if index >= 13:
                price += 0.7
            benchmark_rows.append(
                {
                    "entity_id": f"benchmark:{benchmark_ticker}",
                    "ticker": benchmark_ticker,
                    "eodhd_symbol": f"{benchmark_ticker}.US",
                    "source_table": "benchmark_prices",
                    "trade_date": trade_date.isoformat(),
                    "open": round(price - 0.2, 4),
                    "high": round(price + 0.2, 4),
                    "low": round(price - 0.4, 4),
                    "close": round(price, 4),
                    "adjusted_close": round(price, 4),
                    "volume": float(5_000_000 + index * 10_000),
                    "fetched_at_utc": "2026-04-12T00:00:00+00:00",
                }
            )

    pd.DataFrame(company_rows).to_parquet(settings.processed_dir / "market_prices_daily.parquet", index=False)
    pd.DataFrame(benchmark_rows).to_parquet(settings.processed_dir / "benchmark_prices_daily.parquet", index=False)


def _event_row(event_id: str, article_id: str, published_at: str) -> dict:
    return {
        "event_id": event_id,
        "article_id": article_id,
        "classifier_version": "test",
        "headline": "Hyperscaler AI infrastructure demand continues to expand",
        "source": "Example Wire",
        "source_url": f"https://example.com/{article_id}",
        "canonical_url": f"https://example.com/{article_id}",
        "published_at_utc": published_at,
        "summary": "Theme-heavy AI infrastructure event.",
        "origin_companies": json.dumps([]),
        "mentioned_companies": json.dumps([]),
        "primary_segment": "ai_accelerators",
        "secondary_segments": json.dumps(["networking", "foundry"]),
        "primary_themes": json.dumps(["AI server demand", "AI networking"]),
        "event_type": "ai_demand_hyperscaler_capex",
        "direction": "positive",
        "severity": "high",
        "confidence": 0.84,
        "reasoning": "Theme-first event.",
        "market_relevance_score": 0.9,
        "processed_at_utc": "2026-04-12T12:05:00+00:00",
    }


def _theme_rows(event_id: str, article_id: str) -> list[dict]:
    return [
        {
            "event_id": event_id,
            "article_id": article_id,
            "theme_id": "theme:ai_server_demand",
            "theme_name": "AI server demand",
            "mapping_sources": json.dumps(["event_type_default"]),
            "matched_keywords": json.dumps(["ai demand"]),
            "related_tickers": json.dumps([]),
            "match_score": 1.9,
            "is_primary": True,
            "processed_at_utc": "2026-04-12T12:05:00+00:00",
        },
        {
            "event_id": event_id,
            "article_id": article_id,
            "theme_id": "theme:ai_networking",
            "theme_name": "AI networking",
            "mapping_sources": json.dumps(["event_type_default"]),
            "matched_keywords": json.dumps(["networking"]),
            "related_tickers": json.dumps([]),
            "match_score": 1.6,
            "is_primary": True,
            "processed_at_utc": "2026-04-12T12:05:00+00:00",
        },
    ]


def _run_graph_and_scoring_pipeline(settings: Settings, force: bool = True) -> None:
    GraphBuildService(settings).run()
    GraphPropagationService(settings).run(force=force)
    LagModelingService(settings).run(force=force)
    ExposureScoringService(settings).run(force=force)


def test_lag_and_exposure_scoring_build_ranked_impacts(tmp_path):
    settings = _build_test_settings(tmp_path)
    _write_reference_parquets(settings)
    _write_events(
        settings,
        events=[_event_row("event_1", "article_1", "2026-04-02T12:00:00+00:00")],
        themes=_theme_rows("event_1", "article_1"),
    )

    _run_graph_and_scoring_pipeline(settings)

    lag_predictions = pd.read_parquet(settings.processed_dir / "event_lag_predictions.parquet")
    scores = pd.read_parquet(settings.processed_dir / "event_impact_scores.parquet")

    assert {"NVDA", "AVGO", "TSM"}.issubset(set(scores["ticker"]))
    assert {"NVDA", "TSM"}.issubset(set(lag_predictions["ticker"]))

    ordered_buckets = {"same_day": 0, "1d": 1, "3d": 2, "5d": 3, "10d": 4}
    nvda_bucket = lag_predictions.loc[lag_predictions["ticker"] == "NVDA", "predicted_lag_bucket"].iloc[0]
    tsm_bucket = lag_predictions.loc[lag_predictions["ticker"] == "TSM", "predicted_lag_bucket"].iloc[0]
    assert ordered_buckets[tsm_bucket] >= ordered_buckets[nvda_bucket]

    tsm_score = scores.loc[scores["ticker"] == "TSM"].iloc[0]
    assert tsm_score["predicted_lag_bucket"] in ordered_buckets
    assert tsm_score["total_rank_score"] > 0
    assert bool(tsm_score["is_non_obvious"]) is True
    assert tsm_score["historical_similarity_score"] == 0


def test_market_evaluation_computes_reactions_and_empirical_lag_feedback(tmp_path):
    settings = _build_test_settings(tmp_path)
    _write_reference_parquets(settings)
    _write_market_prices(settings)

    _write_events(
        settings,
        events=[_event_row("event_1", "article_1", "2026-04-02T12:00:00+00:00")],
        themes=_theme_rows("event_1", "article_1"),
    )
    _run_graph_and_scoring_pipeline(settings)
    MarketEvaluationService(settings).run(force=True)

    reactions = pd.read_parquet(settings.processed_dir / "event_market_reactions.parquet")
    tsm_reaction = reactions.loc[reactions["ticker"] == "TSM"].iloc[0]
    assert tsm_reaction["best_signed_abnormal_return"] > 0
    assert tsm_reaction["realized_lag_bucket"] in {"3d", "5d", "10d"}
    assert bool(tsm_reaction["hit_flag"]) is True

    _write_events(
        settings,
        events=[
            _event_row("event_1", "article_1", "2026-04-02T12:00:00+00:00"),
            _event_row("event_2", "article_2", "2026-04-20T12:00:00+00:00"),
        ],
        themes=_theme_rows("event_1", "article_1") + _theme_rows("event_2", "article_2"),
    )
    GraphPropagationService(settings).run(force=True)
    LagModelingService(settings).run(force=True)

    lag_predictions = pd.read_parquet(settings.processed_dir / "event_lag_predictions.parquet")
    event_two_tsm = lag_predictions[
        (lag_predictions["event_id"] == "event_2") & (lag_predictions["ticker"] == "TSM")
    ].iloc[0]
    assert event_two_tsm["empirical_support_count"] >= 1
    assert "empirical_scope:" in event_two_tsm["lag_reason_codes"]

    ExposureScoringService(settings).run(force=True)
    MarketEvaluationService(settings).run(force=True)
    summary = pd.read_parquet(settings.processed_dir / "evaluation_summary.parquet")
    assert not summary.empty
    assert "delayed_impact_hit_rate" in set(summary["metric_name"])
