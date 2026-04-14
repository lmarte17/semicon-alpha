from __future__ import annotations

import argparse
import logging

import uvicorn

from semicon_alpha.api.main import create_app
from semicon_alpha.evaluation import MarketEvaluationService
from semicon_alpha.events import EventIntelligenceService
from semicon_alpha.graph import GraphBuildService, GraphPropagationService
from semicon_alpha.ingestion.fmp import FMPIngestionService
from semicon_alpha.ingestion.lithos import LithosIngestionService
from semicon_alpha.ingestion.reference import ReferenceDataService
from semicon_alpha.ingestion.source_enrichment import SourceEnrichmentService
from semicon_alpha.llm import ArticleTriageService, GeminiClient
from semicon_alpha.llm.config import LLMStructuredCallConfig, ModelTier
from semicon_alpha.llm.prompts import (
    ARTICLE_TRIAGE_PROMPT_VERSION,
    ARTICLE_TRIAGE_SYSTEM_PROMPT,
)
from semicon_alpha.llm.schemas import ArticleTriageResponse
from semicon_alpha.retrieval import RetrievalIndexService
from semicon_alpha.scoring import ExposureScoringService, LagModelingService
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.logging import configure_logging


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Semicon Alpha ingestion CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("news-snapshot", help="Fetch and parse the Lithos semicon page")

    news_enrich = subparsers.add_parser(
        "news-enrich", help="Fetch and enrich discovered source articles"
    )
    news_enrich.add_argument("--limit", type=int, default=25)
    news_enrich.add_argument("--force", action="store_true")

    article_triage = subparsers.add_parser(
        "article-triage", help="Run Gemini-backed relevance triage over enriched articles"
    )
    article_triage.add_argument("--limit", type=int, default=50)
    article_triage.add_argument("--force", action="store_true")

    event_sync = subparsers.add_parser(
        "event-sync", help="Convert enriched articles into structured event intelligence datasets"
    )
    event_sync.add_argument("--limit", type=int, default=50)
    event_sync.add_argument("--force", action="store_true")

    subparsers.add_parser(
        "graph-sync", help="Build unified graph nodes and edges from reference datasets"
    )

    subparsers.add_parser(
        "retrieval-sync", help="Build the hybrid retrieval index for terminal search"
    )

    graph_propagate = subparsers.add_parser(
        "graph-propagate", help="Generate event graph anchors and propagated influence outputs"
    )
    graph_propagate.add_argument("--limit", type=int, default=50)
    graph_propagate.add_argument("--force", action="store_true")

    lag_sync = subparsers.add_parser(
        "lag-sync", help="Generate lag-model predictions for event-company impact candidates"
    )
    lag_sync.add_argument("--limit", type=int, default=50)
    lag_sync.add_argument("--force", action="store_true")

    score_sync = subparsers.add_parser(
        "score-sync", help="Rank company impacts using graph influence, lag, and historical evaluation"
    )
    score_sync.add_argument("--limit", type=int, default=50)
    score_sync.add_argument("--force", action="store_true")

    evaluate_sync = subparsers.add_parser(
        "evaluate-sync", help="Evaluate scored event impacts against realized market moves"
    )
    evaluate_sync.add_argument("--limit", type=int, default=50)
    evaluate_sync.add_argument("--force", action="store_true")

    serve = subparsers.add_parser("serve", help="Run the Wave 1 intelligence terminal locally")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    market_sync = subparsers.add_parser(
        "market-sync", help="Fetch FMP daily price history for the curated universe"
    )
    market_sync.add_argument("--start", required=True, help="Start date in YYYY-MM-DD format")
    market_sync.add_argument("--end", help="Optional end date in YYYY-MM-DD format")

    reference_sync = subparsers.add_parser(
        "reference-sync", help="Build reference datasets and fetch company profiles"
    )
    reference_sync.add_argument("--skip-exchange-symbols", action="store_true")

    ingest_all = subparsers.add_parser(
        "ingest-all", help="Run news, reference, market ingestion, and event intelligence together"
    )
    ingest_all.add_argument("--start", required=True, help="Start date in YYYY-MM-DD format")
    ingest_all.add_argument("--end", help="Optional end date in YYYY-MM-DD format")
    ingest_all.add_argument("--enrich-limit", type=int, default=25)
    ingest_all.add_argument("--event-limit", type=int, default=50)
    ingest_all.add_argument("--skip-exchange-symbols", action="store_true")

    subparsers.add_parser("db-sync", help="Refresh DuckDB views over processed parquet datasets")
    subparsers.add_parser("llm-check", help="Run a Gemini structured-output connectivity check")

    return parser


def main() -> None:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()
    settings = Settings()
    settings.ensure_directories()

    lithos_service = LithosIngestionService(settings)
    enrichment_service = SourceEnrichmentService(settings)
    article_triage_service = ArticleTriageService(settings)
    event_service = EventIntelligenceService(settings)
    graph_build_service = GraphBuildService(settings)
    graph_propagation_service = GraphPropagationService(settings)
    retrieval_service = RetrievalIndexService(settings)
    lag_service = LagModelingService(settings)
    scoring_service = ExposureScoringService(settings)
    evaluation_service = MarketEvaluationService(settings)
    market_service = FMPIngestionService(settings)
    reference_service = ReferenceDataService(settings, market_service)
    catalog = DuckDBCatalog(settings)

    if args.command == "news-snapshot":
        result = lithos_service.run()
        LOGGER.info("Captured Lithos snapshot %s with %s articles", result["snapshot_id"], result["article_count"])
        return

    if args.command == "news-enrich":
        result = enrichment_service.run(limit=args.limit, force=args.force)
        LOGGER.info("Enriched %s articles", result["processed_count"])
        return

    if args.command == "article-triage":
        if not settings.llm_runtime_enabled:
            raise RuntimeError(
                "LLM runtime is not enabled. Set GEMINI_API_KEY in the environment or .env."
            )
        enriched_path = settings.processed_dir / "news_articles_enriched.parquet"
        if not enriched_path.exists():
            LOGGER.info("No enriched article dataset found; nothing to triage")
            return
        import pandas as pd

        enriched = pd.read_parquet(enriched_path)
        candidates = event_service._prepare_candidate_frame(enriched)  # noqa: SLF001
        candidates = candidates.head(args.limit)
        result = article_triage_service.run(candidates, force=args.force)
        LOGGER.info("Triaged %s articles", len(result))
        return

    if args.command == "event-sync":
        result = event_service.run(limit=args.limit, force=args.force)
        LOGGER.info(
            "Structured %s events with %s entity mentions, %s classifications, %s theme mappings, %s LLM reviews, %s fusion decisions, and filtered %s articles via triage",
            result["event_count"],
            result["entity_count"],
            result["classification_count"],
            result["theme_count"],
            result["llm_review_count"],
            result["llm_fusion_count"],
            result["triage_filtered_count"],
        )
        return

    if args.command == "graph-sync":
        result = graph_build_service.run()
        LOGGER.info(
            "Built graph datasets with %s nodes, %s edges, and %s graph changes",
            result["node_count"],
            result["edge_count"],
            result["change_count"],
        )
        return

    if args.command == "retrieval-sync":
        result = retrieval_service.run()
        LOGGER.info(
            "Built retrieval index with %s records and %s embedding rows",
            result["record_count"],
            result["embedding_count"],
        )
        return

    if args.command == "graph-propagate":
        result = graph_propagation_service.run(limit=args.limit, force=args.force)
        LOGGER.info(
            "Propagated %s events into %s anchors, %s paths, and %s node influence rows",
            result["event_count"],
            result["anchor_count"],
            result["path_count"],
            result["influence_count"],
        )
        return

    if args.command == "lag-sync":
        result = lag_service.run(limit=args.limit, force=args.force)
        LOGGER.info(
            "Generated %s lag predictions across %s events with %s empirical profiles",
            result["prediction_count"],
            result["event_count"],
            result["profile_count"],
        )
        return

    if args.command == "score-sync":
        if args.force or not lag_service.predictions_path.exists():
            lag_service.run(limit=args.limit, force=args.force)
        result = scoring_service.run(limit=args.limit, force=args.force)
        LOGGER.info(
            "Scored %s event-company impacts across %s events",
            result["score_count"],
            result["event_count"],
        )
        return

    if args.command == "evaluate-sync":
        result = evaluation_service.run(limit=args.limit, force=args.force)
        LOGGER.info(
            "Evaluated %s scored impacts across %s events and refreshed %s summary metrics",
            result["reaction_count"],
            result["event_count"],
            result["summary_count"],
        )
        return

    if args.command == "serve":
        uvicorn.run(
            create_app(settings),
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return

    if args.command == "market-sync":
        result = market_service.sync_market_data(start=args.start, end=args.end)
        LOGGER.info("Fetched %s company rows and %s benchmark rows", result["company_rows"], result["benchmark_rows"])
        return

    if args.command == "reference-sync":
        result = reference_service.sync_reference_data(skip_exchange_symbols=args.skip_exchange_symbols)
        LOGGER.info(
            "Reference sync complete with %s companies, %s themes, %s ontology nodes, %s relationships, %s fundamentals",
            result["company_count"],
            result["theme_count"],
            result["ontology_node_count"],
            result["relationship_count"],
            result["fundamental_count"],
        )
        return

    if args.command == "ingest-all":
        snapshot = lithos_service.run()
        enriched = enrichment_service.run(limit=args.enrich_limit, force=False)
        reference = reference_service.sync_reference_data(
            skip_exchange_symbols=args.skip_exchange_symbols
        )
        market = market_service.sync_market_data(start=args.start, end=args.end)
        events = event_service.run(limit=args.event_limit, force=False)
        LOGGER.info(
            "All ingestion complete: snapshot=%s articles=%s enriched=%s events=%s company_rows=%s benchmark_rows=%s companies=%s",
            snapshot["snapshot_id"],
            snapshot["article_count"],
            enriched["processed_count"],
            events["event_count"],
            market["company_rows"],
            market["benchmark_rows"],
            reference["company_count"],
        )
        return

    if args.command == "db-sync":
        result = catalog.refresh_processed_views()
        LOGGER.info("DuckDB catalog refreshed for %s datasets", result["dataset_count"])
        return

    if args.command == "llm-check":
        if not settings.llm_runtime_enabled:
            raise RuntimeError(
                "LLM runtime is not enabled. Set GEMINI_API_KEY in the environment or .env."
            )
        client = GeminiClient(settings)
        result = client.generate_structured(
            config=LLMStructuredCallConfig(
                workflow="llm_check",
                prompt_version=ARTICLE_TRIAGE_PROMPT_VERSION,
                schema_name="ArticleTriageResponse",
                schema_version="1",
                model_tier=ModelTier.FLASH,
                temperature=0.0,
                max_output_tokens=250,
            ),
            system_prompt=ARTICLE_TRIAGE_SYSTEM_PROMPT,
            user_prompt=(
                "Headline: TSMC says advanced packaging capacity remains tight.\n"
                "Source: Test\n"
                "Source URL: https://example.com/test\n"
                "Canonical URL: https://example.com/test\n"
                "Published At: 2026-04-13T00:00:00+00:00\n\n"
                "Description:\nAdvanced packaging constraints continue to affect AI accelerator supply.\n\n"
                "Excerpt:\nNone\n\n"
                "Discovered Summary Snippet:\nNone\n\n"
                "Body Text:\nTSMC and Amkor discussed advanced packaging bottlenecks tied to AI server demand.\n\n"
                "Return only a JSON object that matches the required schema."
            ),
            response_model=ArticleTriageResponse,
        )
        LOGGER.info(
            "LLM check succeeded with model %s and confidence %.2f",
            result.model_name,
            result.parsed.confidence,
        )
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
