import json

import httpx
import pandas as pd

from semicon_alpha.events import EventIntelligenceService
from semicon_alpha.graph import GraphBuildService
from semicon_alpha.llm import GeminiClient
from semicon_alpha.llm.workflows import ArticleTriageService, EventReviewService, GeminiEmbeddingService
from semicon_alpha.retrieval import RetrievalIndexService
from semicon_alpha.services import EvidenceService, EventWorkspaceService, ResearchService, SearchService, WorldModelRepository
from tests.test_llm_wave0_wave1 import _build_test_settings
from tests.test_scoring_evaluation import _event_row, _theme_rows, _write_events, _write_reference_parquets


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
            "promptTokenCount": 120,
            "candidatesTokenCount": 50,
        },
    }


def _embedding_response(values: list[float]) -> dict:
    return {
        "embedding": {
            "values": values,
        }
    }


def test_event_review_service_overrides_low_confidence_deterministic_result(tmp_path):
    settings = _build_test_settings(tmp_path, GEMINI_API_KEY="test-key")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_structured_response(
                {
                    "selected_event_type": "export_control_policy",
                    "selected_direction": "negative",
                    "selected_severity": "high",
                    "summary": "New export controls tighten advanced lithography shipments to China fabs.",
                    "reasoning_summary": "The article explicitly describes export-control restrictions on advanced lithography tools.",
                    "suggested_origin_companies": ["ASML"],
                    "suggested_mentioned_companies": ["TSM", "INTC"],
                    "suggested_regulators": ["U.S. Commerce Department"],
                    "suggested_countries": ["China", "United States"],
                    "suggested_technologies": ["EUV lithography"],
                    "suggested_facilities": [],
                    "suggested_primary_theme_ids": ["theme:wafer_fab_equipment"],
                    "suggested_secondary_theme_ids": ["theme:leading_edge_logic"],
                    "suggested_primary_segment": "wafer_fab_equipment",
                    "suggested_secondary_segments": ["foundry"],
                    "time_horizon_hint": "immediate",
                    "evidence_spans": ["tighten export controls", "advanced lithography tools"],
                    "uncertainty_flags": ["policy_scope_may_expand"],
                    "confidence": 0.92,
                    "abstain": False,
                    "needs_review": False,
                    "review_notes": "Policy wording is clear enough for an override.",
                }
            ),
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    service = EventReviewService(settings, client=GeminiClient(settings, http_client=http_client))

    result = service.review(
        event_id="event_test",
        article={
            "article_id": "article_test",
            "headline": "New export rules hit ASML tool shipments to China fabs",
            "source": "Policy Wire",
            "source_url": "https://example.com/policy",
            "published_at_utc": "2026-04-13T10:00:00+00:00",
            "description": "New rules limit shipments of advanced lithography tools.",
            "excerpt": None,
            "body_text": "The rules tighten export controls on advanced lithography systems to China fabs, adding pressure on ASML, TSMC, and Intel.",
        },
        deterministic={
            "event_type": "unclassified_semiconductor_event",
            "direction": "ambiguous",
            "severity": "medium",
            "confidence": 0.31,
            "summary": "Fallback event",
            "reasoning": "Weak deterministic evidence.",
            "origin_companies": [],
            "mentioned_companies": ["ASML"],
            "primary_segment": None,
            "secondary_segments": [],
            "primary_themes": [],
            "primary_theme_ids": [],
        },
        classification_candidates=[{"event_type": "unclassified_semiconductor_event", "score": 0.1, "matched_keywords": []}],
        tracked_companies={"ASML": "ASML Holding", "TSM": "Taiwan Semiconductor Manufacturing", "INTC": "Intel"},
        theme_names={
            "theme:wafer_fab_equipment": "Wafer Fab Equipment",
            "theme:leading_edge_logic": "Leading Edge Logic",
        },
    )

    assert result.final_event_type == "export_control_policy"
    assert result.final_direction == "negative"
    assert result.final_severity == "high"
    assert result.extraction_method == "deterministic_plus_llm_override"
    assert result.llm_review_status == "override_applied"
    assert result.fusion_record.decision == "llm_override"
    assert result.entity_records
    assert result.theme_records
    http_client.close()


def test_event_sync_writes_wave2_llm_sidecars(tmp_path):
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
                "title": "TSMC says CoWoS capacity remains tight as HBM demand builds",
                "site_name": "Semicon Daily",
                "author": "Analyst Writer",
                "excerpt": "Advanced packaging constraints remain in focus.",
                "description": "AI infrastructure demand is keeping advanced packaging tight.",
                "body_text": "TSMC said CoWoS advanced packaging capacity remains tight as HBM demand continues to build for AI accelerators.",
                "raw_html_path": "raw1.html",
                "content_sha256": "abc123",
                "error_message": None,
            }
        ]
    )
    discovered = pd.DataFrame(
        [
            {
                "article_id": "article1",
                "title": "TSMC says CoWoS capacity remains tight as HBM demand builds",
                "summary_snippet": "Packaging article",
                "source_domain": "semicondaily.example.com",
            }
        ]
    )
    enriched.to_parquet(settings.processed_dir / "news_articles_enriched.parquet", index=False)
    discovered.to_parquet(settings.processed_dir / "news_articles_discovered.parquet", index=False)

    responses = [
        _structured_response(
            {
                "relevance_label": "relevant_event",
                "is_semiconductor_relevant": True,
                "is_event_worthy": True,
                "article_type": "capacity",
                "primary_subjects": ["advanced packaging"],
                "mentioned_companies": ["TSM"],
                "mentioned_technologies": ["CoWoS", "HBM"],
                "mentioned_countries": ["Taiwan"],
                "confidence": 0.9,
                "abstain": False,
                "needs_review": False,
                "rejection_reason": None,
                "reasoning_summary": "The article is directly about semiconductor packaging constraints.",
            }
        ),
        _structured_response(
            {
                "selected_event_type": "advanced_packaging_capacity",
                "selected_direction": "negative",
                "selected_severity": "high",
                "summary": "TSMC says advanced packaging remains tight as HBM demand builds.",
                "reasoning_summary": "CoWoS and HBM language support a packaging-capacity bottleneck.",
                "suggested_origin_companies": ["TSM"],
                "suggested_mentioned_companies": ["TSM"],
                "suggested_regulators": [],
                "suggested_countries": ["Taiwan"],
                "suggested_technologies": ["CoWoS", "HBM"],
                "suggested_facilities": [],
                "suggested_primary_theme_ids": ["theme:advanced_packaging", "theme:hbm_demand"],
                "suggested_secondary_theme_ids": ["theme:ai_server_demand"],
                "suggested_primary_segment": "foundry",
                "suggested_secondary_segments": ["advanced_packaging"],
                "time_horizon_hint": "near_term",
                "evidence_spans": ["CoWoS capacity remains tight", "HBM demand continues to build"],
                "uncertainty_flags": ["capacity_duration_unclear"],
                "confidence": 0.87,
                "abstain": False,
                "needs_review": False,
                "review_notes": "LLM agrees with the deterministic core classification.",
            }
        ),
    ]
    state = {"index": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        payload = responses[state["index"]]
        state["index"] += 1
        return httpx.Response(200, json=payload)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    service = EventIntelligenceService(settings)
    service.article_triage_service = ArticleTriageService(
        settings,
        client=GeminiClient(settings, http_client=http_client),
    )
    service.event_review_service = EventReviewService(
        settings,
        client=GeminiClient(settings, http_client=http_client),
    )

    result = service.run(force=True)

    assert result["event_count"] == 1
    assert result["llm_review_count"] == 1
    assert result["llm_fusion_count"] == 1

    events = pd.read_parquet(settings.processed_dir / "news_events_structured.parquet")
    llm_reviews = pd.read_parquet(settings.processed_dir / "event_llm_reviews.parquet")
    fusion = pd.read_parquet(settings.processed_dir / "event_llm_fusion_decisions.parquet")
    llm_entities = pd.read_parquet(settings.processed_dir / "event_llm_entities.parquet")
    llm_themes = pd.read_parquet(settings.processed_dir / "event_llm_themes.parquet")

    event_row = events.iloc[0]
    assert event_row["extraction_method"] == "deterministic_plus_llm_review"
    assert event_row["llm_review_status"] in {"reviewed", "disagreement"}
    assert json.loads(event_row["evidence_spans"])
    assert llm_reviews.iloc[0]["event_id"] == event_row["event_id"]
    assert fusion.iloc[0]["decision"] in {"llm_enrichment", "deterministic_retained"}
    assert any(row["entity_type"] == "technology" for row in llm_entities.to_dict(orient="records"))
    assert any(row["theme_id"] == "theme:hbm_demand" for row in llm_themes.to_dict(orient="records"))
    http_client.close()


def test_retrieval_sync_builds_embedding_dataset_when_enabled(tmp_path):
    settings = _build_test_settings(tmp_path, GEMINI_API_KEY="test-key")
    _write_reference_parquets(settings)
    GraphBuildService(settings).run()
    _write_events(
        settings,
        events=[_event_row("event_1", "article_1", "2026-04-02T12:00:00+00:00")],
        themes=_theme_rows("event_1", "article_1"),
    )
    pd.DataFrame(
        [
            {
                "article_id": "article_1",
                "source_url": "https://example.com/article-1",
                "canonical_url": "https://example.com/article-1",
                "fetch_status": "success",
                "http_status": 200,
                "content_type": "text/html",
                "fetched_at_utc": "2026-04-02T13:00:00+00:00",
                "published_at_utc": "2026-04-02T12:00:00+00:00",
                "title": "Advanced packaging remains constrained in Taiwan",
                "site_name": "Semicon News",
                "author": "Desk",
                "excerpt": "Packaging remains constrained.",
                "description": "Taiwan fabs remain central to packaging scale-up.",
                "body_text": "Taiwan fabs remain central to advanced packaging scale-up for AI accelerators.",
                "raw_html_path": "article1.html",
                "content_sha256": "doc-1",
                "error_message": None,
            }
        ]
    ).to_parquet(settings.processed_dir / "news_articles_enriched.parquet", index=False)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        text = payload["content"]["parts"][0]["text"].lower()
        if "taiwan" in text:
            return httpx.Response(200, json=_embedding_response([1.0, 0.0, 0.0]))
        if "advanced packaging" in text:
            return httpx.Response(200, json=_embedding_response([0.0, 1.0, 0.0]))
        return httpx.Response(200, json=_embedding_response([0.0, 0.0, 1.0]))

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    service = RetrievalIndexService(settings)
    service.embedding_service = GeminiEmbeddingService(
        settings,
        client=GeminiClient(settings, http_client=http_client),
    )

    result = service.run()

    assert result["record_count"] > 0
    assert result["embedding_count"] > 0

    embeddings = pd.read_parquet(settings.processed_dir / "retrieval_embeddings.parquet")
    index = pd.read_parquet(settings.processed_dir / "retrieval_index.parquet")
    assert not embeddings.empty
    assert index["embedding_model"].notna().any()
    assert index["chunk_count"].min() >= 1
    http_client.close()


def test_search_service_uses_model_embeddings_for_semantic_lookup(tmp_path):
    settings = _build_test_settings(tmp_path, GEMINI_API_KEY="test-key")
    _write_reference_parquets(settings)
    GraphBuildService(settings).run()
    _write_events(
        settings,
        events=[
            _event_row("event_1", "article_1", "2026-04-02T12:00:00+00:00"),
            _event_row("event_2", "article_2", "2026-04-10T12:00:00+00:00"),
        ],
        themes=_theme_rows("event_1", "article_1") + _theme_rows("event_2", "article_2"),
    )
    pd.DataFrame(
        [
            {
                "article_id": "article_1",
                "source_url": "https://example.com/article-1",
                "canonical_url": "https://example.com/article-1",
                "fetch_status": "success",
                "http_status": 200,
                "content_type": "text/html",
                "fetched_at_utc": "2026-04-02T13:00:00+00:00",
                "published_at_utc": "2026-04-02T12:00:00+00:00",
                "title": "Taiwan advanced packaging scale-up",
                "site_name": "Semicon News",
                "author": "Desk",
                "excerpt": "Packaging remains constrained.",
                "description": "Taiwan fabs remain central.",
                "body_text": "Taiwan fabs remain central to advanced packaging scale-up.",
                "raw_html_path": "article1.html",
                "content_sha256": "doc-1",
                "error_message": None,
            }
        ]
    ).to_parquet(settings.processed_dir / "news_articles_enriched.parquet", index=False)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        text = payload["content"]["parts"][0]["text"].lower()
        if "island fabs" in text or "taiwan" in text:
            return httpx.Response(200, json=_embedding_response([1.0, 0.0, 0.0]))
        if "advanced packaging" in text:
            return httpx.Response(200, json=_embedding_response([0.0, 1.0, 0.0]))
        return httpx.Response(200, json=_embedding_response([0.0, 0.0, 1.0]))

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    retrieval_service = RetrievalIndexService(settings)
    retrieval_service.embedding_service = GeminiEmbeddingService(
        settings,
        client=GeminiClient(settings, http_client=http_client),
    )
    retrieval_service.run()

    repo = WorldModelRepository(settings)
    search_service = SearchService(repo, settings)
    search_service.embedding_service = GeminiEmbeddingService(
        settings,
        client=GeminiClient(settings, http_client=http_client),
    )

    results = search_service.search("island fabs", limit=5)
    assert any(row["id"] == "country:taiwan" for row in results["entities"])

    research = ResearchService(repo, EventWorkspaceService(repo, EvidenceService(repo)))
    analogs = research.get_event_analogs("event_1")
    assert analogs
    assert any("semantic match" in " ".join(item["similarity_reasons"]) for item in analogs)
    http_client.close()
