from fastapi.testclient import TestClient

from semicon_alpha.api import create_app
from semicon_alpha.retrieval import RetrievalIndexService
from tests.test_scoring_evaluation import (
    _build_test_settings,
    _event_row,
    _run_graph_and_scoring_pipeline,
    _theme_rows,
    _write_events,
    _write_reference_parquets,
)


def test_wave5_ontology_search_and_history_endpoints(tmp_path):
    settings = _build_test_settings(tmp_path)
    _write_reference_parquets(settings)
    _write_events(
        settings,
        events=[_event_row("event_1", "article_1", "2026-04-02T12:00:00+00:00")],
        themes=_theme_rows("event_1", "article_1"),
    )
    _run_graph_and_scoring_pipeline(settings)
    RetrievalIndexService(settings).run()

    client = TestClient(create_app(settings))

    countries = client.get("/api/entities", params={"node_type": "country"})
    assert countries.status_code == 200
    assert any(row["node_id"] == "country:taiwan" for row in countries.json())

    search = client.get("/api/search", params={"q": "Taiwan advanced packaging"})
    assert search.status_code == 200
    assert any(row["id"] == "country:taiwan" for row in search.json()["entities"])

    entity = client.get("/api/entities/country:taiwan")
    assert entity.status_code == 200
    payload = entity.json()
    assert payload["entity"]["node_type"] == "country"
    assert payload["history"]
    assert payload["recent_events"]

    history = client.get("/api/entities/country:taiwan/history")
    assert history.status_code == 200
    assert history.json()
