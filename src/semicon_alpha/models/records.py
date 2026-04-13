from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


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
    source_table: str
    is_derived: bool = False


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
