import json

import httpx
import pandas as pd
from fastapi.testclient import TestClient

from semicon_alpha.api import create_app
from semicon_alpha.llm import GeminiClient
from semicon_alpha.llm.workflows import AnalystSynthesisService
from tests.test_wave4_scenarios_theses_api import _build_client


def _structured_response(payload: dict) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(payload),
                        }
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 140,
            "candidatesTokenCount": 90,
        },
    }


def test_wave4_copilot_synthesis_writes_sidecar_and_returns_grounded_sections(tmp_path):
    client, settings = _build_client(tmp_path)
    settings.llm_enabled = True
    settings.gemini_api_key = "test-key"
    response_payload = _structured_response(
        {
            "answer": "TSM matters because the event raises foundry and packaging constraints that can propagate into its revenue timing and ecosystem positioning.",
            "observations": [
                "The event is classified as a positive demand signal.",
                "TSM appears in the ranked impact candidates for the event.",
            ],
            "inferences": [
                "TSM can benefit indirectly through foundry and packaging demand exposure.",
            ],
            "uncertainties": [
                "The timing of the realized move could still lag the initial event date.",
            ],
            "next_checks": [
                "Inspect the top retained TSM propagation paths.",
            ],
            "citations_used": ["c1"],
            "confidence": 0.86,
            "abstain": False,
            "needs_review": False,
        }
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client.app.state.services.copilot.synthesis_service = AnalystSynthesisService(
        settings,
        client=GeminiClient(settings, http_client=http_client),
    )

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
    assert payload["uncertainties"]
    assert payload["next_checks"]
    assert payload["citations"]

    sidecar = pd.read_parquet(settings.processed_dir / "copilot_llm_responses.parquet")
    assert not sidecar.empty
    assert sidecar.iloc[0]["scope_type"] == "event"
    assert sidecar.iloc[0]["synthesis_status"] == "synthesized"
    http_client.close()


def test_wave4_report_synthesis_uses_pro_for_scenario_memo_and_persists_sidecar(tmp_path):
    client, settings = _build_client(tmp_path)
    settings.llm_enabled = True
    settings.gemini_api_key = "test-key"

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
    scenario_id = scenario.json()["scenario"]["scenario_id"]

    captured: dict[str, str] = {}
    response_payload = _structured_response(
        {
            "summary": "The scenario remains constructive because retained assumption pathways still point toward positive AI demand transmission.",
            "observations": [
                "The scenario contains explicit positive AI demand assumptions.",
                "Retained impacted entities include tracked semiconductor names.",
            ],
            "inferences": [
                "Positive AI demand still supports second-order beneficiaries in the current graph.",
            ],
            "uncertainties": [
                "Contradictory signals could still emerge if demand softens.",
            ],
            "next_checks": [
                "Monitor contradiction signals and rerun after new event flow.",
            ],
            "citations_used": [],
            "markdown_body": "## Scenario Readout\n- Positive AI demand assumptions remain active.\n- The current path set still supports tracked beneficiaries.",
            "confidence": 0.88,
            "abstain": False,
            "needs_review": False,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=response_payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client.app.state.services.reports.synthesis_service = AnalystSynthesisService(
        settings,
        client=GeminiClient(settings, http_client=http_client),
    )

    report = client.post(
        "/api/reports/generate",
        json={"report_type": "scenario_memo", "scenario_id": scenario_id},
    )
    assert report.status_code == 200
    payload = report.json()
    assert "Scenario Memo" in payload["title"]
    assert "Scenario Readout" in payload["markdown"]
    assert settings.gemini_pro_model in captured["url"]

    sidecar = pd.read_parquet(settings.processed_dir / "report_llm_generations.parquet")
    assert not sidecar.empty
    assert sidecar.iloc[0]["report_id"] == payload["report_id"]
    assert sidecar.iloc[0]["report_type"] == "scenario_memo"
    assert sidecar.iloc[0]["synthesis_status"] == "synthesized"
    http_client.close()
