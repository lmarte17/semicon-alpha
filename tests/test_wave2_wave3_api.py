from pathlib import Path

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


def _build_client(tmp_path: Path, two_events: bool = False) -> tuple[TestClient, object]:
    settings = _build_test_settings(tmp_path)
    _write_reference_parquets(settings)
    _write_market_prices(settings)
    events = [_event_row("event_1", "article_1", "2026-04-02T12:00:00+00:00")]
    themes = _theme_rows("event_1", "article_1")
    if two_events:
        events.append(_event_row("event_2", "article_2", "2026-04-20T12:00:00+00:00"))
        themes.extend(_theme_rows("event_2", "article_2"))
    _write_events(settings, events=events, themes=themes)
    _run_graph_and_scoring_pipeline(settings)
    MarketEvaluationService(settings).run(force=True)
    return TestClient(create_app(settings)), settings


def test_wave2_watchlists_alerts_and_notes(tmp_path):
    client, _settings = _build_client(tmp_path)

    watchlist = client.post("/api/watchlists", json={"name": "TSM Monitor"})
    assert watchlist.status_code == 200
    watchlist_id = watchlist.json()["watchlist"]["watchlist_id"]

    add_item = client.post(
        f"/api/watchlists/{watchlist_id}/items",
        json={"item_type": "entity", "item_id": "company:TSM"},
    )
    assert add_item.status_code == 200

    note = client.post(
        "/api/notes",
        json={
            "subject_type": "entity",
            "subject_id": "company:TSM",
            "title": "Risk view",
            "body": "TSM should underperform if this setup weakens.",
            "stance": "negative",
        },
    )
    assert note.status_code == 200

    workspace = client.get(f"/api/watchlists/{watchlist_id}")
    assert workspace.status_code == 200
    payload = workspace.json()
    assert payload["items"]
    assert payload["event_feed"]

    alerts = client.get("/api/alerts", params={"refresh": "true"})
    assert alerts.status_code == 200
    alert_types = {row["alert_type"] for row in alerts.json()["alerts"]}
    assert "watch_event" in alert_types
    assert "contradiction" in alert_types


def test_wave2_boards_queries_and_reports(tmp_path):
    client, settings = _build_client(tmp_path)

    board = client.post("/api/boards", json={"name": "AI Supply Chain"})
    assert board.status_code == 200
    board_id = board.json()["board"]["board_id"]

    add_entity = client.post(
        f"/api/boards/{board_id}/items",
        json={"item_type": "entity", "item_id": "company:TSM"},
    )
    assert add_entity.status_code == 200

    query = client.post(
        "/api/queries",
        json={"name": "TSM Search", "query_text": "TSM"},
    )
    assert query.status_code == 200
    query_id = query.json()["query_id"]

    query_run = client.get(f"/api/queries/{query_id}/run")
    assert query_run.status_code == 200
    assert any(row["id"] == "company:TSM" for row in query_run.json()["results"]["entities"])

    report = client.post(
        "/api/reports/generate",
        json={"report_type": "weekly_thematic_brief", "board_id": board_id},
    )
    assert report.status_code == 200
    report_id = report.json()["report_id"]

    pin_report = client.post(
        f"/api/boards/{board_id}/items",
        json={"item_type": "report", "item_id": report_id, "title": report.json()["title"]},
    )
    assert pin_report.status_code == 200

    board_payload = client.get(f"/api/boards/{board_id}")
    assert board_payload.status_code == 200
    assert board_payload.json()["reports"]

    report_path = settings.outputs_dir / "reports" / f"{report_id.replace(':', '_')}.md"
    assert report_path.exists()


def test_wave3_analogs_backtest_and_event_report(tmp_path):
    client, _settings = _build_client(tmp_path, two_events=True)

    analogs = client.get("/api/events/event_1/analogs")
    assert analogs.status_code == 200
    analog_payload = analogs.json()
    assert analog_payload
    assert analog_payload[0]["event_id"] == "event_2"

    backtest = client.get("/api/events/event_1/backtest")
    assert backtest.status_code == 200
    backtest_payload = backtest.json()
    assert backtest_payload["predicted_vs_realized"]
    assert backtest_payload["summary"]["candidate_count"] >= 1

    report = client.post(
        "/api/reports/generate",
        json={"report_type": "event_impact_brief", "event_id": "event_1"},
    )
    assert report.status_code == 200
    report_payload = report.json()
    assert "Event Impact Brief" in report_payload["title"]
    assert "Hyperscaler AI infrastructure demand continues to expand" in report_payload["markdown"]
