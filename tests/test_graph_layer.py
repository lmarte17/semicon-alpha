import json
import shutil
from pathlib import Path

import pandas as pd
import yaml

from semicon_alpha.graph import GraphBuildService, GraphPropagationService
from semicon_alpha.graph.query import build_multidigraph, get_neighbors
from semicon_alpha.settings import Settings


REPO_ROOT = Path(__file__).resolve().parents[1]


def _build_test_settings(tmp_path: Path) -> Settings:
    project_root = tmp_path / "project"
    configs_dir = project_root / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    for config_name in (
        "graph_schema.yaml",
        "ontology_nodes.yaml",
        "relationship_edges.yaml",
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


def test_graph_build_service_creates_expected_nodes_and_edges(tmp_path):
    settings = _build_test_settings(tmp_path)
    _write_reference_parquets(settings)

    result = GraphBuildService(settings).run()

    assert result["node_count"] > 0
    assert result["edge_count"] > 0

    nodes = pd.read_parquet(settings.processed_dir / "graph_nodes.parquet")
    edges = pd.read_parquet(settings.processed_dir / "graph_edges.parquet")

    assert "company:NVDA" in set(nodes["node_id"])
    assert "theme:ai_server_demand" in set(nodes["node_id"])
    assert "segment:ai_accelerators" in set(nodes["node_id"])
    assert "country:taiwan" in set(nodes["node_id"])
    assert "facility:tsmc_fab18" in set(nodes["node_id"])

    segment_edge = edges[
        (edges["source_node_id"] == "company:NVDA") & (edges["edge_type"] == "in_segment_primary")
    ].iloc[0]
    assert segment_edge["target_node_id"] == "segment:ai_accelerators"
    assert bool(segment_edge["is_derived"]) is True

    graph = build_multidigraph(
        settings.processed_dir / "graph_nodes.parquet",
        settings.processed_dir / "graph_edges.parquet",
    )
    neighbors = get_neighbors(graph, "theme:ai_server_demand")
    incoming_sources = {row["source_node_id"] for row in neighbors["incoming"]}
    assert {"company:NVDA", "company:AMD"}.issubset(incoming_sources)

    history = pd.read_parquet(settings.processed_dir / "graph_node_history.parquet")
    change_log = pd.read_parquet(settings.processed_dir / "graph_change_log.parquet")
    assert not history.empty
    assert not change_log.empty


def test_graph_propagation_service_handles_theme_only_event(tmp_path):
    settings = _build_test_settings(tmp_path)
    _write_reference_parquets(settings)
    GraphBuildService(settings).run()

    events = pd.DataFrame(
        [
            {
                "event_id": "event_theme_only",
                "article_id": "article_theme_only",
                "classifier_version": "test",
                "headline": "AI infrastructure partnerships continue to drive networking demand",
                "source": "Example Wire",
                "source_url": "https://example.com/ai-networking",
                "canonical_url": "https://example.com/ai-networking",
                "published_at_utc": "2026-04-12T12:00:00+00:00",
                "summary": "Theme-heavy event with no tracked origin company.",
                "origin_companies": json.dumps([]),
                "mentioned_companies": json.dumps([]),
                "primary_segment": "ai_accelerators",
                "secondary_segments": json.dumps(["networking"]),
                "primary_themes": json.dumps(["AI server demand", "AI networking"]),
                "event_type": "ai_demand_hyperscaler_capex",
                "direction": "positive",
                "severity": "high",
                "confidence": 0.82,
                "reasoning": "Theme-first event.",
                "market_relevance_score": 0.91,
                "processed_at_utc": "2026-04-12T12:05:00+00:00",
            }
        ]
    )
    events.to_parquet(settings.processed_dir / "news_events_structured.parquet", index=False)

    event_themes = pd.DataFrame(
        [
            {
                "event_id": "event_theme_only",
                "article_id": "article_theme_only",
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
                "event_id": "event_theme_only",
                "article_id": "article_theme_only",
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
    )
    event_themes.to_parquet(settings.processed_dir / "news_event_themes.parquet", index=False)

    result = GraphPropagationService(settings).run(force=True)

    assert result["event_count"] == 1
    assert result["anchor_count"] >= 3
    assert result["path_count"] > 0
    assert result["influence_count"] > 0

    anchors = pd.read_parquet(settings.processed_dir / "event_graph_anchors.parquet")
    anchor_nodes = set(anchors["anchor_node_id"])
    assert {"theme:ai_server_demand", "theme:ai_networking", "segment:ai_accelerators"}.issubset(
        anchor_nodes
    )

    influences = pd.read_parquet(settings.processed_dir / "event_node_influence.parquet")
    influence_nodes = set(influences["node_id"])
    assert {"company:NVDA", "company:AMD", "company:AVGO"}.issubset(influence_nodes)
    assert "company:TSM" in influence_nodes

    tsm_row = influences.loc[influences["node_id"] == "company:TSM"].iloc[0]
    assert tsm_row["best_hop_count"] >= 2
    assert tsm_row["aggregate_influence_score"] > 0
    assert tsm_row["provisional_direction"] == "positive"

    paths = pd.read_parquet(settings.processed_dir / "event_propagation_paths.parquet")
    tsm_paths = paths.loc[paths["target_node_id"] == "company:TSM"]
    assert not tsm_paths.empty
    assert tsm_paths["hop_count"].min() >= 2
