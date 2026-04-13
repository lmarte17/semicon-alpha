from fastapi.testclient import TestClient

from semicon_alpha.api import create_app
from semicon_alpha.evaluation import MarketEvaluationService
from tests.test_scoring_evaluation import (
    _build_test_settings,
    _event_row,
    _run_graph_and_scoring_pipeline,
    _theme_rows,
    _write_events,
    _write_market_prices,
    _write_reference_parquets,
)


def _build_client(tmp_path) -> TestClient:
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
    return TestClient(create_app(settings))


def test_wave1_dashboard_and_terminal_shell(tmp_path):
    client = _build_client(tmp_path)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    terminal = client.get("/terminal")
    assert terminal.status_code == 200
    assert "Semicon Alpha" in terminal.text

    dashboard = client.get("/api/dashboard/overview")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["metrics"]["event_count"] == 1
    assert payload["recent_events"][0]["event_id"] == "event_1"
    assert payload["top_non_obvious_impacts"]


def test_wave1_event_entity_search_and_path_endpoints(tmp_path):
    client = _build_client(tmp_path)

    event = client.get("/api/events/event_1")
    assert event.status_code == 200
    event_payload = event.json()
    assert event_payload["event"]["headline"]
    assert event_payload["impact_candidates"]
    assert event_payload["supporting_evidence"]["source_documents"]

    impacts = client.get("/api/events/event_1/impacts")
    assert impacts.status_code == 200
    assert {row["ticker"] for row in impacts.json()} >= {"NVDA", "TSM"}

    entity = client.get("/api/entities/company:TSM")
    assert entity.status_code == 200
    entity_payload = entity.json()
    assert entity_payload["entity"]["label"]
    assert entity_payload["neighbors"]["incoming"] or entity_payload["neighbors"]["outgoing"]
    assert entity_payload["recent_events"]

    search = client.get("/api/search", params={"q": "TSM"})
    assert search.status_code == 200
    assert any(row["id"] == "company:TSM" for row in search.json()["entities"])

    path_trace = client.post(
        "/api/graph/path-trace",
        json={
            "source_id": "theme:ai_server_demand",
            "target_id": "company:TSM",
            "max_hops": 4,
            "max_paths": 3,
        },
    )
    assert path_trace.status_code == 200
    assert path_trace.json()["paths"]


def test_wave1_copilot_returns_grounded_scoped_answer(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/api/copilot/query",
        json={
            "query": "Why does this event matter to TSM?",
            "event_id": "event_1",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "TSM" in payload["answer"]
    assert payload["observations"]
    assert payload["citations"]
