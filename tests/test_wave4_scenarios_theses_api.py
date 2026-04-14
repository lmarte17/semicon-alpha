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


def _build_client(tmp_path: Path) -> tuple[TestClient, object]:
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
    return TestClient(create_app(settings)), settings


def test_wave4_scenario_workspace_and_alerts(tmp_path):
    client, _settings = _build_client(tmp_path)

    scenario = client.post(
        "/api/scenarios",
        json={
            "name": "AI Demand Up",
            "assumptions": [
                {
                    "item_type": "theme",
                    "item_id": "theme:ai_server_demand",
                    "direction": "positive",
                }
            ],
        },
    )
    assert scenario.status_code == 200
    scenario_payload = scenario.json()
    scenario_id = scenario_payload["scenario"]["scenario_id"]
    assert scenario_payload["assumptions"]
    assert scenario_payload["latest_run"]
    assert scenario_payload["latest_run"]["impacted_entities_json"]

    workspace = client.get(f"/api/scenarios/{scenario_id}")
    assert workspace.status_code == 200
    workspace_payload = workspace.json()
    assert workspace_payload["support_signals"]
    impacted_tickers = {row["ticker"] for row in workspace_payload["latest_run"]["impacted_entities_json"]}
    assert {"NVDA", "TSM"}.intersection(impacted_tickers)

    alerts = client.get("/api/alerts", params={"refresh": "true"})
    assert alerts.status_code == 200
    alert_types = {row["alert_type"] for row in alerts.json()["alerts"]}
    assert "scenario_support" in alert_types


def test_wave4_thesis_monitoring_and_reports(tmp_path):
    client, settings = _build_client(tmp_path)

    scenario = client.post(
        "/api/scenarios",
        json={
            "name": "AI Networking Continues",
            "assumptions": [
                {
                    "item_type": "theme",
                    "item_id": "theme:ai_networking",
                    "direction": "positive",
                }
            ],
        },
    )
    assert scenario.status_code == 200
    scenario_id = scenario.json()["scenario"]["scenario_id"]

    thesis = client.post(
        "/api/theses",
        json={
            "title": "TSM benefits from AI demand",
            "statement": "TSM should benefit as AI server demand continues to expand through foundry and packaging demand.",
            "stance": "positive",
            "links": [
                {"item_type": "entity", "item_id": "company:TSM"},
                {"item_type": "scenario", "item_id": scenario_id},
            ],
            "initial_update": "Initial thesis created from explicit AI demand assumptions.",
        },
    )
    assert thesis.status_code == 200
    thesis_payload = thesis.json()
    thesis_id = thesis_payload["thesis"]["thesis_id"]
    assert thesis_payload["links"]
    assert thesis_payload["updates"]
    assert thesis_payload["support_signals"]

    thesis_update = client.post(
        f"/api/theses/{thesis_id}/updates",
        json={"summary": "Confidence increased after supportive event flow.", "confidence": 0.72},
    )
    assert thesis_update.status_code == 200

    thesis_workspace = client.get(f"/api/theses/{thesis_id}")
    assert thesis_workspace.status_code == 200
    thesis_workspace_payload = thesis_workspace.json()
    assert thesis_workspace_payload["support_signals"]
    assert thesis_workspace_payload["thesis"]["confidence"] == 0.72

    scenario_report = client.post(
        "/api/reports/generate",
        json={"report_type": "scenario_memo", "scenario_id": scenario_id},
    )
    assert scenario_report.status_code == 200
    assert "Scenario Memo" in scenario_report.json()["title"]

    thesis_report = client.post(
        "/api/reports/generate",
        json={"report_type": "thesis_change_report", "thesis_id": thesis_id},
    )
    assert thesis_report.status_code == 200
    thesis_report_payload = thesis_report.json()
    assert "Thesis Change Report" in thesis_report_payload["title"]

    report_path = settings.outputs_dir / "reports" / f"{thesis_report_payload['report_id'].replace(':', '_')}.md"
    assert report_path.exists()

    alerts = client.get("/api/alerts", params={"refresh": "true"})
    assert alerts.status_code == 200
    alert_types = {row["alert_type"] for row in alerts.json()["alerts"]}
    assert "thesis_support" in alert_types
