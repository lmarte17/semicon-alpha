import json
import shutil
from pathlib import Path

import httpx
import pandas as pd

from semicon_alpha.events import EventIntelligenceService
from semicon_alpha.llm.client import GeminiClient
from semicon_alpha.llm.config import LLMStructuredCallConfig, ModelTier
from semicon_alpha.llm.prompts import (
    ARTICLE_TRIAGE_PROMPT_VERSION,
    ARTICLE_TRIAGE_SYSTEM_PROMPT,
)
from semicon_alpha.llm.schemas import ArticleTriageResponse
from semicon_alpha.llm.workflows import ArticleTriageService
from semicon_alpha.settings import Settings


REPO_ROOT = Path(__file__).resolve().parents[1]


def _build_test_settings(tmp_path: Path, **overrides) -> Settings:
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
    settings = Settings(project_root=project_root, **overrides)
    settings.ensure_directories()
    return settings


def _mock_http_client(response_payload: dict, captured: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=response_payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gemini_client_parses_structured_output_with_mock_transport(tmp_path):
    settings = _build_test_settings(tmp_path, GEMINI_API_KEY="test-key")
    captured: dict = {}
    response_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "relevance_label": "relevant_event",
                                    "is_semiconductor_relevant": True,
                                    "is_event_worthy": True,
                                    "article_type": "supply_chain",
                                    "primary_subjects": ["advanced packaging"],
                                    "mentioned_companies": ["TSMC", "NVDA"],
                                    "mentioned_technologies": ["CoWoS"],
                                    "mentioned_countries": ["Taiwan"],
                                    "confidence": 0.92,
                                    "abstain": False,
                                    "needs_review": False,
                                    "rejection_reason": None,
                                    "reasoning_summary": "The article is directly about semiconductor packaging constraints.",
                                }
                            )
                        }
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 120,
            "candidatesTokenCount": 34,
        },
    }
    http_client = _mock_http_client(response_payload, captured)
    client = GeminiClient(settings, http_client=http_client)

    result = client.generate_structured(
        config=LLMStructuredCallConfig(
            workflow="article_triage",
            prompt_version=ARTICLE_TRIAGE_PROMPT_VERSION,
            schema_name="ArticleTriageResponse",
            schema_version="1",
            model_tier=ModelTier.FLASH,
        ),
        system_prompt=ARTICLE_TRIAGE_SYSTEM_PROMPT,
        user_prompt="Review this article.",
        response_model=ArticleTriageResponse,
    )

    assert result.parsed.relevance_label == "relevant_event"
    assert result.parsed.is_semiconductor_relevant is True
    assert "responseSchema" in captured["payload"]["generationConfig"]
    assert captured["headers"]["x-goog-api-key"] == "test-key"
    assert settings.gemini_flash_model in captured["url"]
    http_client.close()


def test_article_triage_service_writes_triage_and_job_logs(tmp_path):
    settings = _build_test_settings(tmp_path, GEMINI_API_KEY="test-key")
    captured: dict = {}
    response_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "relevance_label": "relevant_event",
                                    "is_semiconductor_relevant": True,
                                    "is_event_worthy": True,
                                    "article_type": "capacity",
                                    "primary_subjects": ["advanced packaging"],
                                    "mentioned_companies": ["TSMC", "AMKR"],
                                    "mentioned_technologies": ["CoWoS"],
                                    "mentioned_countries": ["Taiwan"],
                                    "confidence": 0.88,
                                    "abstain": False,
                                    "needs_review": False,
                                    "rejection_reason": None,
                                    "reasoning_summary": "The article describes semiconductor packaging capacity constraints.",
                                }
                            )
                        }
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 40,
        },
    }
    http_client = _mock_http_client(response_payload, captured)
    service = ArticleTriageService(
        settings,
        client=GeminiClient(settings, http_client=http_client),
    )
    frame = pd.DataFrame(
        [
            {
                "article_id": "article-1",
                "source_url": "https://example.com/semicon",
                "canonical_url": "https://example.com/semicon",
                "title": "TSMC says CoWoS packaging capacity remains tight",
                "site_name": "Semicon News",
                "description": "Packaging capacity remains tight for AI accelerators.",
                "excerpt": "Advanced packaging remains constrained.",
                "body_text": "TSMC and Amkor said advanced packaging remains tight for AI demand.",
                "discovered_summary_snippet": "Packaging constraints for AI accelerators.",
                "content_sha256": "abc123",
            }
        ]
    )

    result = service.run(frame, force=True)

    assert len(result) == 1
    triage = pd.read_parquet(settings.processed_dir / "article_llm_triage.parquet")
    assert triage.iloc[0]["article_id"] == "article-1"
    assert triage.iloc[0]["relevance_label"] == "relevant_event"
    assert json.loads(triage.iloc[0]["mentioned_companies"]) == ["TSMC", "AMKR"]

    logs = pd.read_parquet(settings.processed_dir / "llm_job_runs.parquet")
    assert logs.iloc[0]["workflow"] == "article_triage"
    assert logs.iloc[0]["status"] == "success"
    assert int(logs.iloc[0]["input_token_count"]) == 100
    http_client.close()


def test_event_sync_filters_confidently_irrelevant_articles_using_triage(tmp_path):
    settings = _build_test_settings(tmp_path, GEMINI_API_KEY="test-key")

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
                    "demand and HBM demand continue to build for Nvidia and AMD accelerators."
                ),
                "raw_html_path": "raw1.html",
                "content_sha256": "abc123",
                "error_message": None,
            },
            {
                "article_id": "article2",
                "source_url": "https://news.example.com/phone-review",
                "canonical_url": "https://news.example.com/phone-review",
                "fetch_status": "success",
                "http_status": 200,
                "content_type": "text/html",
                "fetched_at_utc": "2026-04-12T01:00:00+00:00",
                "published_at_utc": "2026-04-11T18:00:00+00:00",
                "title": "New smartphone camera features wow consumers",
                "site_name": "Consumer Tech",
                "author": "Tech Desk",
                "excerpt": "A consumer phone review.",
                "description": "The latest flagship phone introduces new camera tools.",
                "body_text": "This article is about smartphone camera quality and battery life.",
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
                "title": "Packaging fallback title",
                "summary_snippet": "Packaging article",
                "source_domain": "semicondaily.example.com",
            },
            {
                "article_id": "article2",
                "title": "Phone review fallback title",
                "summary_snippet": "Phone review article",
                "source_domain": "consumertech.example.com",
            },
        ]
    )
    discovered.to_parquet(settings.processed_dir / "news_articles_discovered.parquet", index=False)

    service = EventIntelligenceService(settings)
    service.article_triage_service.run = lambda frame, force=False: pd.DataFrame(
        [
            {
                "article_id": "article1",
                "confidence": 0.92,
                "abstain": False,
                "needs_review": False,
                "is_semiconductor_relevant": True,
                "is_event_worthy": True,
            },
            {
                "article_id": "article2",
                "confidence": 0.96,
                "abstain": False,
                "needs_review": False,
                "is_semiconductor_relevant": False,
                "is_event_worthy": False,
            },
        ]
    )

    result = service.run(force=True)

    assert result["event_count"] == 1
    assert result["triage_count"] == 2
    assert result["triage_filtered_count"] == 1
    events = pd.read_parquet(settings.processed_dir / "news_events_structured.parquet")
    assert set(events["article_id"]) == {"article1"}
