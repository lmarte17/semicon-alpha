from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FlatRecordModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    def as_flat_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="python")


class SnapshotMetadata(FlatRecordModel):
    snapshot_id: str
    topic: str
    source_url: str
    fetched_at_utc: datetime
    site_written_at_utc: datetime | None = None
    http_status: int
    etag: str | None = None
    last_modified: str | None = None
    raw_path: str
    content_sha256: str


class SourceRegistryRecord(FlatRecordModel):
    source_id: str
    source_slug: str
    source_domain: str
    lithos_source_url: str
    freshness_text: str | None = None
    status_flag: str | None = None
    icon_id: str | None = None
    source_topic: str = "semicon"
    scraped_at_utc: datetime
    snapshot_id: str


class ArticleObservationRecord(FlatRecordModel):
    observation_id: str
    article_id: str
    snapshot_id: str
    discovered_at_utc: datetime
    source_url: str
    title: str
    summary_snippet: str | None = None
    source_domain: str
    source_slug: str | None = None
    icon_id: str | None = None
    lithos_age_bucket_label: str | None = None
    lithos_age_bucket_hours: int | None = None
    is_urgent: bool = False
    image_url: str | None = None
    position_index: int


class DiscoveredArticleRecord(FlatRecordModel):
    article_id: str
    source_url: str
    title: str
    summary_snippet: str | None = None
    source_domain: str
    source_slug: str | None = None
    icon_id: str | None = None
    first_discovered_at_utc: datetime
    last_seen_at_utc: datetime
    latest_snapshot_id: str
    latest_lithos_age_bucket_label: str | None = None
    latest_lithos_age_bucket_hours: int | None = None
    latest_is_urgent: bool = False
    latest_image_url: str | None = None
    latest_position_index: int
    observation_count: int = 1


class EnrichedArticleRecord(FlatRecordModel):
    article_id: str
    source_url: str
    canonical_url: str | None = None
    fetch_status: str
    http_status: int | None = None
    content_type: str | None = None
    fetched_at_utc: datetime
    published_at_utc: datetime | None = None
    title: str | None = None
    site_name: str | None = None
    author: str | None = None
    excerpt: str | None = None
    description: str | None = None
    body_text: str | None = None
    raw_html_path: str | None = None
    content_sha256: str | None = None
    error_message: str | None = None


class LLMJobRunRecord(FlatRecordModel):
    job_id: str
    workflow: str
    source_id: str
    status: str
    model_name: str
    prompt_version: str
    schema_name: str
    schema_version: str
    request_hash: str
    latency_ms: int | None = None
    input_token_count: int | None = None
    output_token_count: int | None = None
    cached_input_token_count: int | None = None
    error_message: str | None = None
    response_preview: str | None = None
    metadata_json: dict[str, Any] | list[Any] | None = None
    started_at_utc: datetime
    completed_at_utc: datetime


class ArticleLLMTriageRecord(FlatRecordModel):
    article_id: str
    source_url: str
    canonical_url: str | None = None
    source: str
    headline: str
    content_sha256: str | None = None
    relevance_label: str
    is_semiconductor_relevant: bool
    is_event_worthy: bool
    article_type: str
    primary_subjects: list[str]
    mentioned_companies: list[str]
    mentioned_technologies: list[str]
    mentioned_countries: list[str]
    confidence: float
    abstain: bool
    needs_review: bool
    rejection_reason: str | None = None
    reasoning_summary: str
    model_name: str
    prompt_version: str
    schema_version: str
    processed_at_utc: datetime


class CopilotLLMResponseRecord(FlatRecordModel):
    response_id: str
    query_text: str
    scope_type: str
    scope_id: str | None = None
    answer: str
    observations: list[str]
    inferences: list[str]
    uncertainties: list[str]
    next_checks: list[str]
    citations_used: list[str]
    related_entity_ids: list[str]
    related_event_ids: list[str]
    confidence: float
    abstain: bool
    needs_review: bool
    synthesis_status: str
    model_name: str
    prompt_version: str
    schema_version: str
    created_at_utc: datetime


class EventLLMReviewRecord(FlatRecordModel):
    event_id: str
    article_id: str
    deterministic_event_type: str
    llm_event_type: str | None = None
    deterministic_direction: str
    llm_direction: str | None = None
    deterministic_severity: str
    llm_severity: str | None = None
    llm_summary: str | None = None
    llm_reasoning_summary: str
    confidence: float
    abstain: bool
    needs_review: bool
    disagreement_flags: list[str]
    evidence_spans: list[str]
    uncertainty_flags: list[str]
    time_horizon_hint: str | None = None
    model_name: str
    prompt_version: str
    schema_version: str
    processed_at_utc: datetime


class EventLLMEntityRecord(FlatRecordModel):
    review_item_id: str
    event_id: str
    article_id: str
    entity_id: str | None = None
    entity_name: str
    entity_type: str
    role_label: str
    evidence_snippets: list[str]
    confidence: float
    model_name: str
    prompt_version: str
    schema_version: str
    processed_at_utc: datetime


class EventLLMThemeRecord(FlatRecordModel):
    review_item_id: str
    event_id: str
    article_id: str
    theme_id: str | None = None
    theme_name: str
    role_label: str
    evidence_snippets: list[str]
    confidence: float
    model_name: str
    prompt_version: str
    schema_version: str
    processed_at_utc: datetime


class EventLLMFusionDecisionRecord(FlatRecordModel):
    event_id: str
    article_id: str
    deterministic_event_type: str
    llm_event_type: str | None = None
    final_event_type: str
    deterministic_direction: str
    llm_direction: str | None = None
    final_direction: str
    deterministic_severity: str
    llm_severity: str | None = None
    final_severity: str
    decision: str
    extraction_method: str
    llm_review_status: str
    disagreement_flags: list[str]
    deterministic_confidence: float
    llm_confidence: float
    review_notes: str | None = None
    model_name: str
    prompt_version: str
    schema_version: str
    processed_at_utc: datetime


class EventEntityMentionRecord(FlatRecordModel):
    event_id: str
    article_id: str
    entity_id: str
    ticker: str
    company_name: str
    matched_aliases: list[str]
    title_aliases: list[str]
    body_aliases: list[str]
    title_mentions: int
    body_mentions: int
    match_score: float
    is_origin_company: bool
    processed_at_utc: datetime


class EventClassificationRecord(FlatRecordModel):
    event_id: str
    article_id: str
    classifier_version: str
    event_type: str
    label: str
    candidate_rank: int
    score: float
    confidence: float
    matched_title_keywords: list[str]
    matched_body_keywords: list[str]
    segment_support: list[str]
    theme_support: list[str]
    is_selected: bool
    processed_at_utc: datetime


class EventThemeMappingRecord(FlatRecordModel):
    event_id: str
    article_id: str
    theme_id: str
    theme_name: str
    mapping_sources: list[str]
    matched_keywords: list[str]
    related_tickers: list[str]
    match_score: float
    is_primary: bool
    processed_at_utc: datetime


class StructuredEventRecord(FlatRecordModel):
    event_id: str
    article_id: str
    classifier_version: str
    headline: str
    source: str
    source_url: str
    canonical_url: str | None = None
    published_at_utc: datetime | None = None
    summary: str
    origin_companies: list[str]
    mentioned_companies: list[str]
    primary_segment: str | None = None
    secondary_segments: list[str]
    primary_themes: list[str]
    event_type: str
    direction: str
    severity: str
    confidence: float
    reasoning: str
    market_relevance_score: float
    extraction_method: str = "deterministic"
    llm_review_status: str | None = None
    evidence_spans: list[str] = Field(default_factory=list)
    uncertainty_flags: list[str] = Field(default_factory=list)
    review_notes: str | None = None
    processed_at_utc: datetime


class GraphNodeRecord(FlatRecordModel):
    node_id: str
    node_type: str
    label: str
    description: str | None = None
    source_table: str
    ticker: str | None = None
    segment_primary: str | None = None
    metadata_json: dict[str, Any] | list[Any] | None = None
    is_active: bool = True
    created_at_utc: datetime


class GraphEdgeRecord(FlatRecordModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    source_node_type: str
    target_node_type: str
    edge_type: str
    weight: float
    sign: str
    confidence: float
    evidence: str | None = None
    evidence_url: str | None = None
    last_updated: str
    effective_start: str | None = None
    effective_end: str | None = None
    relationship_status: str = "active"
    source_table: str
    is_derived: bool = False
    metadata_json: dict[str, Any] | list[Any] | None = None


class GraphNodeHistoryRecord(FlatRecordModel):
    snapshot_id: str
    snapshot_at_utc: datetime
    node_id: str
    node_type: str
    label: str
    description: str | None = None
    source_table: str
    ticker: str | None = None
    segment_primary: str | None = None
    metadata_json: dict[str, Any] | list[Any] | None = None
    is_active: bool = True


class GraphEdgeHistoryRecord(FlatRecordModel):
    snapshot_id: str
    snapshot_at_utc: datetime
    edge_id: str
    source_node_id: str
    target_node_id: str
    source_node_type: str
    target_node_type: str
    edge_type: str
    weight: float
    sign: str
    confidence: float
    evidence: str | None = None
    evidence_url: str | None = None
    last_updated: str
    effective_start: str | None = None
    effective_end: str | None = None
    relationship_status: str = "active"
    source_table: str
    is_derived: bool = False
    metadata_json: dict[str, Any] | list[Any] | None = None


class GraphChangeRecord(FlatRecordModel):
    snapshot_id: str
    snapshot_at_utc: datetime
    object_type: str
    object_id: str
    change_type: str
    node_id: str | None = None
    edge_id: str | None = None
    node_type: str | None = None
    edge_type: str | None = None
    label: str | None = None
    source_node_id: str | None = None
    target_node_id: str | None = None
    summary: str
    previous_value_json: dict[str, Any] | list[Any] | None = None
    current_value_json: dict[str, Any] | list[Any] | None = None


class RetrievalIndexRecord(FlatRecordModel):
    item_id: str
    item_type: str
    search_category: str
    title: str
    subtitle: str | None = None
    url: str | None = None
    semantic_text: str
    aliases: list[str]
    lexical_terms: list[str]
    embedding_vector: list[float]
    embedding_model: str | None = None
    embedding_version: str | None = None
    chunk_count: int = 1
    metadata_json: dict[str, Any] | list[Any] | None = None
    updated_at_utc: datetime


class RetrievalEmbeddingRecord(FlatRecordModel):
    embedding_id: str
    item_id: str
    item_type: str
    search_category: str
    chunk_id: str
    chunk_rank: int
    embedding_model: str
    embedding_version: str
    semantic_text: str
    text_sha256: str
    embedding_vector: list[float]
    updated_at_utc: datetime


class ReportLLMGenerationRecord(FlatRecordModel):
    generation_id: str
    report_id: str
    report_type: str
    title: str
    scope_type: str | None = None
    scope_id: str | None = None
    summary: str
    observations: list[str]
    inferences: list[str]
    uncertainties: list[str]
    next_checks: list[str]
    citations_used: list[str]
    confidence: float
    abstain: bool
    needs_review: bool
    synthesis_status: str
    model_name: str
    prompt_version: str
    schema_version: str
    created_at_utc: datetime


class EventGraphAnchorRecord(FlatRecordModel):
    event_id: str
    anchor_node_id: str
    anchor_node_type: str
    anchor_role: str
    anchor_score: float
    anchor_direction: str
    anchor_confidence: float
    anchor_reason: str
    processed_at_utc: datetime


class EventPropagationPathRecord(FlatRecordModel):
    event_id: str
    target_node_id: str
    target_node_type: str
    hop_count: int
    path_rank: int
    path_nodes: list[str]
    path_edges: list[str]
    path_score: float
    path_direction: str
    path_confidence: float
    reason_codes: list[str]
    processed_at_utc: datetime


class EventNodeInfluenceRecord(FlatRecordModel):
    event_id: str
    node_id: str
    node_type: str
    best_hop_count: int
    path_count: int
    direct_path_score: float
    first_order_score: float
    second_order_score: float
    third_order_score: float
    aggregate_influence_score: float
    provisional_direction: str
    confidence: float
    top_paths: list[dict[str, Any]]
    processed_at_utc: datetime


class LagProfileRecord(FlatRecordModel):
    scope_type: str
    scope_key: str
    event_type: str
    sample_size: int
    preferred_lag_bucket: str
    lag_bucket_scores: dict[str, float]
    mean_signed_abnormal_return: float
    confidence: float
    computed_at_utc: datetime


class EventLagPredictionRecord(FlatRecordModel):
    event_id: str
    ticker: str
    entity_id: str
    event_type: str
    impact_direction: str
    market_cap_bucket: str | None = None
    ecosystem_role: str | None = None
    best_hop_count: int
    heuristic_lag_center: float
    predicted_lag_bucket: str
    lag_bucket_scores: dict[str, float]
    delayed_reaction_score: float
    lag_confidence: float
    empirical_support_count: int
    lag_reason_codes: list[str]
    reasoning: str
    processed_at_utc: datetime


class EventImpactScoreRecord(FlatRecordModel):
    event_id: str
    ticker: str
    entity_id: str
    event_type: str
    published_at_utc: datetime | None = None
    impact_direction: str
    best_hop_count: int
    direct_exposure_score: float
    second_order_score: float
    third_order_score: float
    structural_exposure_score: float
    segment_exposure_score: float
    historical_similarity_score: float
    delayed_reaction_score: float
    obviousness_penalty: float
    total_rank_score: float
    confidence: float
    predicted_lag_bucket: str
    lag_confidence: float
    historical_support_count: int
    is_origin_company: bool
    is_mentioned_company: bool
    is_non_obvious: bool
    market_cap_bucket: str | None = None
    ecosystem_role: str | None = None
    primary_segment: str | None = None
    explanation: str
    reason_codes: list[str]
    top_paths: list[dict[str, Any]]
    processed_at_utc: datetime


class EventMarketReactionRecord(FlatRecordModel):
    event_id: str
    ticker: str
    entity_id: str
    event_type: str
    event_published_at_utc: datetime | None = None
    benchmark_ticker: str
    predicted_direction: str
    predicted_lag_bucket: str
    total_rank_score: float
    confidence: float
    is_non_obvious: bool
    market_cap_bucket: str | None = None
    ecosystem_role: str | None = None
    segment_primary: str | None = None
    anchor_trade_date: date | None = None
    realized_return_t0: float | None = None
    realized_return_t1: float | None = None
    realized_return_t3: float | None = None
    realized_return_t5: float | None = None
    realized_return_t10: float | None = None
    abnormal_return_t0: float | None = None
    abnormal_return_t1: float | None = None
    abnormal_return_t3: float | None = None
    abnormal_return_t5: float | None = None
    abnormal_return_t10: float | None = None
    abnormal_volume_t0: float | None = None
    peak_abnormal_volume_t10: float | None = None
    realized_direction: str | None = None
    realized_lag_bucket: str | None = None
    best_signed_abnormal_return: float | None = None
    hit_flag: bool = False
    rank_realized_move: int | None = None
    evaluated_at_utc: datetime


class EvaluationSummaryRecord(FlatRecordModel):
    metric_name: str
    metric_scope: str
    group_key: str | None = None
    top_n: int | None = None
    metric_value: float
    sample_size: int
    computed_at_utc: datetime


class UniverseCompanyConfig(FlatRecordModel):
    ticker: str
    eodhd_symbol: str
    company_name: str
    exchange: str
    country: str
    segment_primary: str
    segment_secondary: list[str]
    ecosystem_role: str
    market_cap_bucket: str
    is_origin_name_candidate: bool
    notes: str | None = None


class BenchmarkConfig(FlatRecordModel):
    ticker: str
    eodhd_symbol: str
    label: str
    benchmark_type: str


class ThemeNodeRecord(FlatRecordModel):
    node_id: str
    theme_name: str
    node_category: str
    description: str


class OntologyNodeRecord(FlatRecordModel):
    node_id: str
    node_type: str
    label: str
    description: str | None = None
    aliases: list[str] = []
    metadata_json: dict[str, Any] | list[Any] | None = None
    is_active: bool = True


class RelationshipEdgeRecord(FlatRecordModel):
    edge_id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    edge_type: str
    weight: float
    sign: str
    confidence: float
    evidence: str | None = None
    evidence_url: str | None = None
    last_updated: str
    effective_start: str | None = None
    effective_end: str | None = None
    relationship_status: str = "active"
    metadata_json: dict[str, Any] | list[Any] | None = None


class CompanyFundamentalRecord(FlatRecordModel):
    entity_id: str
    ticker: str
    eodhd_symbol: str
    fetched_at_utc: datetime
    company_name: str | None = None
    exchange: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    website: str | None = None
    isin: str | None = None
    lei: str | None = None
    cik: str | None = None
    market_capitalization: float | None = None
    shares_outstanding: float | None = None
    updated_at: str | None = None
    raw_json_path: str


class CompanyRegistryRecord(FlatRecordModel):
    entity_id: str
    ticker: str
    eodhd_symbol: str
    company_name: str
    exchange: str
    country: str
    segment_primary: str
    segment_secondary: list[str]
    ecosystem_role: str
    market_cap_bucket: str
    is_origin_name_candidate: bool
    notes: str | None = None
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    website: str | None = None
    isin: str | None = None
    lei: str | None = None
    cik: str | None = None
    reference_last_updated: datetime


class ExchangeSymbolRecord(FlatRecordModel):
    exchange_code: str
    code: str
    name: str | None = None
    country: str | None = None
    currency: str | None = None
    type: str | None = None
    isin: str | None = None
    previous_close: float | None = None
    exchange: str | None = None
    fetched_at_utc: datetime


class MarketPriceRecord(FlatRecordModel):
    entity_id: str
    ticker: str
    eodhd_symbol: str
    source_table: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float | None = None
    volume: float | None = None
    fetched_at_utc: datetime
