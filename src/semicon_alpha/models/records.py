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
