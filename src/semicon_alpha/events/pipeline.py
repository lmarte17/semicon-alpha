from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd

from semicon_alpha.events.taxonomy import EventTaxonomy, EventTypeRule, load_event_taxonomy
from semicon_alpha.llm.workflows import ArticleTriageService
from semicon_alpha.models.records import (
    EventClassificationRecord,
    EventEntityMentionRecord,
    EventThemeMappingRecord,
    RelationshipEdgeRecord,
    StructuredEventRecord,
    ThemeNodeRecord,
    UniverseCompanyConfig,
)
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import load_yaml, now_utc, stable_id, upsert_parquet


LEGAL_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "holding",
    "holdings",
    "inc",
    "incorporated",
    "limited",
    "ltd",
    "n",
    "nv",
    "plc",
}

GENERIC_SINGLE_WORD_ALIASES = {
    "advanced",
    "analog",
    "applied",
    "monolithic",
    "on",
    "taiwan",
    "texas",
    "united",
}

MANUAL_COMPANY_ALIASES: dict[str, list[str]] = {
    "TSM": ["tsmc", "taiwan semiconductor", "taiwan semiconductor manufacturing"],
    "ASX": ["ase", "ase technology"],
    "MU": ["micron"],
    "NVDA": ["nvidia"],
    "AVGO": ["broadcom"],
    "MRVL": ["marvell"],
    "QCOM": ["qualcomm"],
    "TER": ["teradyne"],
    "SNPS": ["synopsys"],
    "CDNS": ["cadence"],
    "HIMX": ["himax"],
    "AMKR": ["amkor"],
    "ASML": ["asml"],
    "INTC": ["intel"],
    "GFS": ["globalfoundries"],
}

THEME_KEYWORDS: dict[str, list[str]] = {
    "theme:advanced_packaging": [
        "advanced packaging",
        "cowos",
        "2 5d packaging",
        "3d packaging",
        "chiplet packaging",
        "substrate shortage",
        "osat",
    ],
    "theme:ai_networking": [
        "ai networking",
        "ethernet switch",
        "interconnect",
        "optical networking",
        "datacenter networking",
    ],
    "theme:ai_power_management": [
        "ai power management",
        "power delivery",
        "power management",
        "power semiconductor",
    ],
    "theme:ai_server_demand": [
        "ai server",
        "gpu demand",
        "hyperscaler capex",
        "training cluster",
        "datacenter demand",
    ],
    "theme:eda_complexity": [
        "eda",
        "design automation",
        "verification tools",
        "design complexity",
    ],
    "theme:foundry_capacity": [
        "foundry capacity",
        "foundry utilization",
        "wafer starts",
        "fab utilization",
        "capacity ramp",
    ],
    "theme:hbm_demand": [
        "hbm",
        "high bandwidth memory",
        "memory demand",
        "dram supply",
        "hbm pricing",
    ],
    "theme:leading_edge_logic": [
        "leading edge",
        "2nm",
        "3nm",
        "5nm",
        "process node",
    ],
    "theme:mature_node_utilization": [
        "mature node",
        "200mm",
        "specialty process",
        "utilization",
    ],
    "theme:memory_pricing": [
        "memory pricing",
        "dram pricing",
        "nand pricing",
        "spot pricing",
        "contract pricing",
    ],
    "theme:wafer_fab_equipment": [
        "wafer fab equipment",
        "lithography tool",
        "etch tool",
        "deposition tool",
        "metrology tool",
        "wfe",
    ],
    "theme:automotive_power_semis": [
        "automotive demand",
        "automotive semiconductor",
        "silicon carbide",
        "power semiconductor",
    ],
}


@dataclass(frozen=True)
class AliasPattern:
    phrase: str
    normalized_phrase: str
    case_sensitive: bool = False


@dataclass(frozen=True)
class CompanyContext:
    ticker: str
    entity_id: str
    company_name: str
    segment_primary: str
    segment_secondary: list[str]
    aliases: list[AliasPattern]


@dataclass
class EntityMention:
    company: CompanyContext
    matched_aliases: list[str]
    title_aliases: list[str]
    body_aliases: list[str]
    title_mentions: int
    body_mentions: int
    match_score: float
    is_origin_company: bool


@dataclass
class ClassificationCandidate:
    rule: EventTypeRule
    score: float
    matched_title_keywords: list[str]
    matched_body_keywords: list[str]
    segment_support: list[str]
    theme_support: list[str]
    is_selected: bool = False
    confidence: float = 0.0

    @property
    def matched_keywords(self) -> list[str]:
        return [*self.matched_title_keywords, *self.matched_body_keywords]


@dataclass
class ThemeMatch:
    theme_id: str
    theme_name: str
    mapping_sources: set[str] = field(default_factory=set)
    matched_keywords: set[str] = field(default_factory=set)
    related_tickers: set[str] = field(default_factory=set)
    match_score: float = 0.0
    is_primary: bool = False


@dataclass(frozen=True)
class ArticleContext:
    article_id: str
    headline: str
    raw_text: str
    title_text: str
    full_text: str
    source: str
    source_url: str
    canonical_url: str | None
    published_at_utc: datetime | None


@dataclass
class ArticleAnalysis:
    event_record: StructuredEventRecord
    entity_records: list[EventEntityMentionRecord]
    classification_records: list[EventClassificationRecord]
    theme_records: list[EventThemeMappingRecord]


class EventIntelligenceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.enriched_article_path = settings.processed_dir / "news_articles_enriched.parquet"
        self.discovered_article_path = settings.processed_dir / "news_articles_discovered.parquet"
        self.event_entity_path = settings.processed_dir / "news_event_entities.parquet"
        self.event_classification_path = settings.processed_dir / "news_event_classifications.parquet"
        self.event_theme_path = settings.processed_dir / "news_event_themes.parquet"
        self.event_path = settings.processed_dir / "news_events_structured.parquet"
        self.taxonomy_path = settings.configs_dir / "event_taxonomy.yaml"
        self.article_triage_service = ArticleTriageService(settings)

    def run(self, limit: int | None = None, force: bool = False) -> dict[str, int]:
        if not self.enriched_article_path.exists():
            return {
                "processed_count": 0,
                "event_count": 0,
                "entity_count": 0,
                "classification_count": 0,
                "theme_count": 0,
                "triage_count": 0,
                "triage_filtered_count": 0,
            }

        enriched = pd.read_parquet(self.enriched_article_path)
        if enriched.empty:
            return {
                "processed_count": 0,
                "event_count": 0,
                "entity_count": 0,
                "classification_count": 0,
                "theme_count": 0,
                "triage_count": 0,
                "triage_filtered_count": 0,
            }

        candidates = self._prepare_candidate_frame(enriched)
        if candidates.empty:
            return {
                "processed_count": 0,
                "event_count": 0,
                "entity_count": 0,
                "classification_count": 0,
                "theme_count": 0,
                "triage_count": 0,
                "triage_filtered_count": 0,
            }

        if not force and self.event_path.exists():
            existing = pd.read_parquet(self.event_path, columns=["article_id"])
            existing_article_ids = set(existing["article_id"].tolist())
            if existing_article_ids:
                candidates = candidates[~candidates["article_id"].isin(existing_article_ids)]

        if limit is not None:
            candidates = candidates.head(limit)

        triage_result = pd.DataFrame()
        triage_filtered_count = 0
        if not candidates.empty and self.settings.llm_runtime_enabled:
            triage_result = self.article_triage_service.run(candidates, force=force)
            candidates, triage_filtered_count = self._apply_triage_filter(candidates, triage_result)

        if candidates.empty:
            return {
                "processed_count": 0,
                "event_count": 0,
                "entity_count": 0,
                "classification_count": 0,
                "theme_count": 0,
                "triage_count": len(triage_result),
                "triage_filtered_count": triage_filtered_count,
            }

        taxonomy = load_event_taxonomy(self.taxonomy_path)
        companies = self._load_company_contexts()
        theme_names = self._load_theme_names()
        company_theme_edges = self._load_company_theme_edges()

        event_records: list[StructuredEventRecord] = []
        entity_records: list[EventEntityMentionRecord] = []
        classification_records: list[EventClassificationRecord] = []
        theme_records: list[EventThemeMappingRecord] = []

        for row in candidates.to_dict(orient="records"):
            analysis = self._analyze_article(
                row=row,
                taxonomy=taxonomy,
                companies=companies,
                theme_names=theme_names,
                company_theme_edges=company_theme_edges,
            )
            event_records.append(analysis.event_record)
            entity_records.extend(analysis.entity_records)
            classification_records.extend(analysis.classification_records)
            theme_records.extend(analysis.theme_records)

        upsert_parquet(
            self.event_path,
            event_records,
            unique_keys=["event_id"],
            sort_by=["published_at_utc", "processed_at_utc"],
        )
        upsert_parquet(
            self.event_entity_path,
            entity_records,
            unique_keys=["event_id", "entity_id"],
            sort_by=["processed_at_utc"],
        )
        upsert_parquet(
            self.event_classification_path,
            classification_records,
            unique_keys=["event_id", "event_type"],
            sort_by=["processed_at_utc"],
        )
        upsert_parquet(
            self.event_theme_path,
            theme_records,
            unique_keys=["event_id", "theme_id"],
            sort_by=["processed_at_utc"],
        )
        self.catalog.refresh_processed_views()
        return {
            "processed_count": len(event_records),
            "event_count": len(event_records),
            "entity_count": len(entity_records),
            "classification_count": len(classification_records),
            "theme_count": len(theme_records),
            "triage_count": len(triage_result),
            "triage_filtered_count": triage_filtered_count,
        }

    def _apply_triage_filter(
        self,
        candidates: pd.DataFrame,
        triage_frame: pd.DataFrame,
    ) -> tuple[pd.DataFrame, int]:
        if triage_frame.empty:
            return candidates, 0
        triage_by_article = {
            str(row["article_id"]): row for row in triage_frame.to_dict(orient="records")
        }
        allowed_article_ids = [
            str(article_id)
            for article_id in candidates["article_id"].astype(str).tolist()
            if self.article_triage_service.should_allow(triage_by_article.get(str(article_id)))
        ]
        filtered = candidates.loc[candidates["article_id"].astype(str).isin(allowed_article_ids)].copy()
        return filtered, max(0, len(candidates) - len(filtered))

    def _prepare_candidate_frame(self, enriched: pd.DataFrame) -> pd.DataFrame:
        frame = enriched.copy()
        frame = frame[frame["fetch_status"] == "success"].copy()
        if frame.empty:
            return frame

        if self.discovered_article_path.exists():
            discovered = pd.read_parquet(
                self.discovered_article_path,
                columns=["article_id", "title", "summary_snippet", "source_domain"],
            ).rename(
                columns={
                    "title": "discovered_title",
                    "summary_snippet": "discovered_summary_snippet",
                    "source_domain": "discovered_source_domain",
                }
            )
            frame = frame.merge(discovered, on="article_id", how="left")
        else:
            frame["discovered_title"] = None
            frame["discovered_summary_snippet"] = None
            frame["discovered_source_domain"] = None

        frame["effective_headline"] = frame.apply(
            lambda row: (
                _coerce_optional_str(row.get("title"))
                or _coerce_optional_str(row.get("discovered_title"))
                or "Untitled source article"
            ),
            axis=1,
        )
        frame["effective_source"] = frame.apply(
            lambda row: (
                _coerce_optional_str(row.get("site_name"))
                or _coerce_optional_str(row.get("discovered_source_domain"))
                or _domain_from_url(_coerce_optional_str(row.get("canonical_url")) or row["source_url"])
            ),
            axis=1,
        )
        frame["published_sort_utc"] = pd.to_datetime(
            frame["published_at_utc"].fillna(frame["fetched_at_utc"]),
            utc=True,
            errors="coerce",
        )
        frame = frame.sort_values("published_sort_utc", ascending=False, na_position="last")
        return frame

    def _analyze_article(
        self,
        row: dict[str, object],
        taxonomy: EventTaxonomy,
        companies: list[CompanyContext],
        theme_names: dict[str, str],
        company_theme_edges: dict[str, list[RelationshipEdgeRecord]],
    ) -> ArticleAnalysis:
        processed_at = now_utc()
        article = self._build_article_context(row)
        event_id = stable_id("event", article.article_id)

        mentions = self._extract_company_mentions(article, companies)
        selected_origins = [mention for mention in mentions if mention.is_origin_company]
        if not selected_origins and mentions:
            selected_origins = [mentions[0]]

        mentioned_theme_ids = {
            edge.target_id
            for mention in mentions
            for edge in company_theme_edges.get(mention.company.ticker, [])
        }
        classifications = self._score_event_types(
            article=article,
            mentions=mentions,
            taxonomy=taxonomy,
            mentioned_theme_ids=mentioned_theme_ids,
        )
        selected_classification = self._select_classification(classifications)

        direction, direction_signals = self._determine_direction(article, selected_classification, taxonomy)
        severity = self._determine_severity(article, selected_classification, taxonomy, selected_origins)
        themes = self._map_themes(
            article=article,
            selected_classification=selected_classification,
            mentions=mentions,
            theme_names=theme_names,
            company_theme_edges=company_theme_edges,
        )
        primary_themes = [theme.theme_name for theme in themes if theme.is_primary]
        primary_segment, secondary_segments = self._derive_segments(mentions, selected_classification)
        confidence = self._estimate_confidence(
            selected_classification=selected_classification,
            classifications=classifications,
            mentions=mentions,
            themes=themes,
            article=article,
        )
        market_relevance_score = self._estimate_market_relevance(
            selected_classification=selected_classification,
            mentions=mentions,
            themes=themes,
            severity=severity,
            article=article,
        )
        summary = self._build_summary(
            headline=article.headline,
            selected_classification=selected_classification,
            origin_companies=[mention.company.ticker for mention in selected_origins],
            theme_names=primary_themes,
            direction=direction,
            severity=severity,
        )
        reasoning = self._build_reasoning(
            selected_classification=selected_classification,
            mentions=mentions,
            themes=themes,
            direction=direction,
            direction_signals=direction_signals,
            severity=severity,
        )

        for candidate in classifications:
            candidate.confidence = confidence if candidate.is_selected else max(0.05, confidence - 0.2)

        event_record = StructuredEventRecord(
            event_id=event_id,
            article_id=article.article_id,
            classifier_version=taxonomy.version,
            headline=article.headline,
            source=article.source,
            source_url=article.source_url,
            canonical_url=article.canonical_url,
            published_at_utc=article.published_at_utc,
            summary=summary,
            origin_companies=[mention.company.ticker for mention in selected_origins],
            mentioned_companies=[mention.company.ticker for mention in mentions],
            primary_segment=primary_segment,
            secondary_segments=secondary_segments,
            primary_themes=primary_themes,
            event_type=selected_classification.rule.event_type,
            direction=direction,
            severity=severity,
            confidence=round(confidence, 4),
            reasoning=reasoning,
            market_relevance_score=round(market_relevance_score, 4),
            processed_at_utc=processed_at,
        )

        entity_records = [
            EventEntityMentionRecord(
                event_id=event_id,
                article_id=article.article_id,
                entity_id=mention.company.entity_id,
                ticker=mention.company.ticker,
                company_name=mention.company.company_name,
                matched_aliases=mention.matched_aliases,
                title_aliases=mention.title_aliases,
                body_aliases=mention.body_aliases,
                title_mentions=mention.title_mentions,
                body_mentions=mention.body_mentions,
                match_score=round(mention.match_score, 4),
                is_origin_company=mention.is_origin_company,
                processed_at_utc=processed_at,
            )
            for mention in mentions
        ]

        classification_records = [
            EventClassificationRecord(
                event_id=event_id,
                article_id=article.article_id,
                classifier_version=taxonomy.version,
                event_type=candidate.rule.event_type,
                label=candidate.rule.label,
                candidate_rank=index,
                score=round(candidate.score, 4),
                confidence=round(candidate.confidence, 4),
                matched_title_keywords=candidate.matched_title_keywords,
                matched_body_keywords=candidate.matched_body_keywords,
                segment_support=candidate.segment_support,
                theme_support=candidate.theme_support,
                is_selected=candidate.is_selected,
                processed_at_utc=processed_at,
            )
            for index, candidate in enumerate(classifications, start=1)
        ]

        theme_records = [
            EventThemeMappingRecord(
                event_id=event_id,
                article_id=article.article_id,
                theme_id=theme.theme_id,
                theme_name=theme.theme_name,
                mapping_sources=sorted(theme.mapping_sources),
                matched_keywords=sorted(theme.matched_keywords),
                related_tickers=sorted(theme.related_tickers),
                match_score=round(theme.match_score, 4),
                is_primary=theme.is_primary,
                processed_at_utc=processed_at,
            )
            for theme in themes
        ]

        return ArticleAnalysis(
            event_record=event_record,
            entity_records=entity_records,
            classification_records=classification_records,
            theme_records=theme_records,
        )

    def _build_article_context(self, row: dict[str, object]) -> ArticleContext:
        headline = _coerce_optional_str(row.get("effective_headline")) or "Untitled source article"
        description = _coerce_optional_str(row.get("description"))
        discovered_summary = _coerce_optional_str(row.get("discovered_summary_snippet"))
        excerpt = _coerce_optional_str(row.get("excerpt"))
        body_text = _coerce_optional_str(row.get("body_text"))
        text_parts = [headline, description, discovered_summary, excerpt, body_text]
        raw_text = " ".join(part for part in text_parts if part)
        full_text = _normalize_text(" ".join(part for part in text_parts if part))
        title_text = _normalize_text(headline)
        return ArticleContext(
            article_id=str(row["article_id"]),
            headline=headline,
            raw_text=raw_text,
            title_text=title_text,
            full_text=full_text,
            source=_coerce_optional_str(row.get("effective_source")) or "unknown",
            source_url=str(row["source_url"]),
            canonical_url=_coerce_optional_str(row.get("canonical_url")),
            published_at_utc=_coerce_optional_datetime(row.get("published_at_utc")),
        )

    def _extract_company_mentions(
        self, article: ArticleContext, companies: list[CompanyContext]
    ) -> list[EntityMention]:
        mentions: list[EntityMention] = []
        for company in companies:
            matched_aliases: list[str] = []
            title_aliases: list[str] = []
            body_aliases: list[str] = []
            title_mentions = 0
            body_mentions = 0
            for alias in company.aliases:
                title_count = _count_alias_matches(
                    normalized_text=article.title_text,
                    raw_text=article.headline,
                    alias=alias,
                )
                full_count = _count_alias_matches(
                    normalized_text=article.full_text,
                    raw_text=article.raw_text,
                    alias=alias,
                )
                body_count = max(0, full_count - title_count)
                if title_count > 0 or body_count > 0:
                    matched_aliases.append(alias.phrase)
                if title_count > 0:
                    title_aliases.append(alias.phrase)
                    title_mentions += title_count
                if body_count > 0:
                    body_aliases.append(alias.phrase)
                    body_mentions += body_count
            if not matched_aliases:
                continue
            unique_matched_aliases = sorted(set(matched_aliases))
            unique_title_aliases = sorted(set(title_aliases))
            unique_body_aliases = sorted(set(body_aliases))
            score = (title_mentions * 1.5) + (body_mentions * 0.75) + (len(unique_matched_aliases) * 0.2)
            mentions.append(
                EntityMention(
                    company=company,
                    matched_aliases=unique_matched_aliases,
                    title_aliases=unique_title_aliases,
                    body_aliases=unique_body_aliases,
                    title_mentions=title_mentions,
                    body_mentions=body_mentions,
                    match_score=score,
                    is_origin_company=title_mentions > 0,
                )
            )
        mentions.sort(key=lambda item: (-item.match_score, item.company.ticker))
        return mentions

    def _score_event_types(
        self,
        article: ArticleContext,
        mentions: list[EntityMention],
        taxonomy: EventTaxonomy,
        mentioned_theme_ids: set[str],
    ) -> list[ClassificationCandidate]:
        mentioned_segments = {
            segment
            for mention in mentions
            for segment in [mention.company.segment_primary, *mention.company.segment_secondary]
        }
        candidates: list[ClassificationCandidate] = []
        fallback_candidate: ClassificationCandidate | None = None
        for rule in taxonomy.event_types:
            title_hits: list[str] = []
            body_hits: list[str] = []
            score = 0.0
            for keyword in rule.keywords:
                if _count_normalized_phrase(article.title_text, keyword):
                    title_hits.append(keyword)
                    score += 2.0
                elif _count_normalized_phrase(article.full_text, keyword):
                    body_hits.append(keyword)
                    score += 1.2
            for keyword in rule.secondary_keywords:
                if _count_normalized_phrase(article.title_text, keyword) and keyword not in title_hits:
                    title_hits.append(keyword)
                    score += 1.25
                elif (
                    _count_normalized_phrase(article.full_text, keyword)
                    and keyword not in body_hits
                    and keyword not in title_hits
                ):
                    body_hits.append(keyword)
                    score += 0.75
            segment_support = sorted(mentioned_segments.intersection(rule.segment_hints))
            theme_support = sorted(mentioned_theme_ids.intersection(rule.theme_ids))
            score += len(segment_support) * 0.45
            score += len(theme_support) * 0.35
            candidate = ClassificationCandidate(
                rule=rule,
                score=score,
                matched_title_keywords=title_hits,
                matched_body_keywords=body_hits,
                segment_support=segment_support,
                theme_support=theme_support,
            )
            candidates.append(candidate)
            if rule.event_type == "unclassified_semiconductor_event":
                fallback_candidate = candidate

        candidates.sort(key=lambda item: (-item.score, item.rule.event_type))
        if candidates and candidates[0].score <= 0 and fallback_candidate is not None:
            candidates = [fallback_candidate, *[item for item in candidates if item is not fallback_candidate]]
        return candidates

    def _select_classification(
        self, classifications: list[ClassificationCandidate]
    ) -> ClassificationCandidate:
        selected = classifications[0]
        selected.is_selected = True
        return selected

    def _determine_direction(
        self,
        article: ArticleContext,
        selected_classification: ClassificationCandidate,
        taxonomy: EventTaxonomy,
    ) -> tuple[str, list[str]]:
        positive_hits = _collect_hits(article, taxonomy.direction_keywords.positive)
        negative_hits = _collect_hits(article, taxonomy.direction_keywords.negative)
        mixed_hits = _collect_hits(article, taxonomy.direction_keywords.mixed)

        positive_score = len(positive_hits)
        negative_score = len(negative_hits)
        if selected_classification.rule.default_direction == "positive":
            positive_score += 1
        elif selected_classification.rule.default_direction == "negative":
            negative_score += 1

        if positive_score == 0 and negative_score == 0:
            if selected_classification.rule.default_direction in {"positive", "negative", "mixed"}:
                return selected_classification.rule.default_direction, mixed_hits
            return "ambiguous", []

        if positive_score > 0 and negative_score > 0:
            if abs(positive_score - negative_score) <= 1 or mixed_hits:
                return "mixed", [*positive_hits[:2], *negative_hits[:2], *mixed_hits[:2]]
            direction = "positive" if positive_score > negative_score else "negative"
            dominant_hits = positive_hits if direction == "positive" else negative_hits
            return direction, dominant_hits[:4]

        if positive_score > 0:
            return "positive", positive_hits[:4]
        return "negative", negative_hits[:4]

    def _determine_severity(
        self,
        article: ArticleContext,
        selected_classification: ClassificationCandidate,
        taxonomy: EventTaxonomy,
        origins: list[EntityMention],
    ) -> str:
        score = {"low": 1, "medium": 2, "high": 3, "critical": 4}[selected_classification.rule.base_severity]
        if _collect_hits(article, taxonomy.severity_keywords.critical):
            score += 2
        elif _collect_hits(article, taxonomy.severity_keywords.high):
            score += 1
        elif _collect_hits(article, taxonomy.severity_keywords.medium):
            score += 0
        if len(origins) >= 2 and selected_classification.score >= 3:
            score += 1
        score = max(1, min(4, score))
        return {1: "low", 2: "medium", 3: "high", 4: "critical"}[score]

    def _map_themes(
        self,
        article: ArticleContext,
        selected_classification: ClassificationCandidate,
        mentions: list[EntityMention],
        theme_names: dict[str, str],
        company_theme_edges: dict[str, list[RelationshipEdgeRecord]],
    ) -> list[ThemeMatch]:
        theme_map: dict[str, ThemeMatch] = {}

        def ensure_theme(theme_id: str) -> ThemeMatch:
            if theme_id not in theme_map:
                theme_map[theme_id] = ThemeMatch(
                    theme_id=theme_id,
                    theme_name=theme_names.get(theme_id, theme_id.removeprefix("theme:").replace("_", " ")),
                )
            return theme_map[theme_id]

        for theme_id in selected_classification.rule.theme_ids:
            theme = ensure_theme(theme_id)
            theme.mapping_sources.add("event_type_default")
            theme.matched_keywords.update(selected_classification.matched_keywords[:4])
            theme.match_score += 1.0 + (selected_classification.score * 0.25)

        for theme_id, keywords in THEME_KEYWORDS.items():
            hits = [
                keyword
                for keyword in keywords
                if _count_normalized_phrase(article.title_text, keyword)
                or _count_normalized_phrase(article.full_text, keyword)
            ]
            if not hits:
                continue
            theme = ensure_theme(theme_id)
            theme.mapping_sources.add("theme_keyword")
            theme.matched_keywords.update(hits)
            theme.match_score += 1.2 + (0.25 * len(hits))

        for mention in mentions:
            for edge in company_theme_edges.get(mention.company.ticker, []):
                theme = ensure_theme(edge.target_id)
                theme.mapping_sources.add("company_theme_edge")
                theme.related_tickers.add(mention.company.ticker)
                if edge.evidence:
                    theme.matched_keywords.add(edge.edge_type)
                theme.match_score += mention.match_score * edge.weight * edge.confidence * 0.4

        themes = sorted(theme_map.values(), key=lambda item: (-item.match_score, item.theme_id))
        for index, theme in enumerate(themes):
            theme.is_primary = index < 2
        return themes

    def _derive_segments(
        self,
        mentions: list[EntityMention],
        selected_classification: ClassificationCandidate,
    ) -> tuple[str | None, list[str]]:
        segment_scores: dict[str, float] = defaultdict(float)
        for hint in selected_classification.rule.segment_hints:
            segment_scores[hint] += 0.75
        for mention in mentions:
            segment_scores[mention.company.segment_primary] += 1.5 * mention.match_score
            for secondary in mention.company.segment_secondary:
                segment_scores[secondary] += 0.75 * mention.match_score
        if not segment_scores:
            return None, []
        ranked_segments = [
            segment for segment, _score in sorted(segment_scores.items(), key=lambda item: (-item[1], item[0]))
        ]
        return ranked_segments[0], ranked_segments[1:4]

    def _estimate_confidence(
        self,
        selected_classification: ClassificationCandidate,
        classifications: list[ClassificationCandidate],
        mentions: list[EntityMention],
        themes: list[ThemeMatch],
        article: ArticleContext,
    ) -> float:
        second_score = classifications[1].score if len(classifications) > 1 else 0.0
        margin_bonus = 0.08 if selected_classification.score - second_score >= 1.0 else 0.0
        entity_bonus = min(0.2, len(mentions) * 0.05)
        theme_bonus = min(0.15, len(themes) * 0.04)
        body_penalty = -0.1 if len(article.full_text) < 40 else 0.0
        confidence = 0.25 + min(0.35, selected_classification.score * 0.07) + entity_bonus + theme_bonus + margin_bonus + body_penalty
        return max(0.05, min(0.98, confidence))

    def _estimate_market_relevance(
        self,
        selected_classification: ClassificationCandidate,
        mentions: list[EntityMention],
        themes: list[ThemeMatch],
        severity: str,
        article: ArticleContext,
    ) -> float:
        classification_strength = min(0.35, selected_classification.score * 0.06)
        entity_strength = min(0.25, sum(mention.match_score for mention in mentions[:3]) * 0.05)
        theme_strength = min(0.2, sum(theme.match_score for theme in themes[:3]) * 0.04)
        severity_bonus = {"low": 0.0, "medium": 0.05, "high": 0.1, "critical": 0.15}[severity]
        text_bonus = 0.05 if len(article.full_text) >= 40 else 0.0
        relevance = 0.1 + classification_strength + entity_strength + theme_strength + severity_bonus + text_bonus
        return max(0.05, min(0.99, relevance))

    def _build_summary(
        self,
        headline: str,
        selected_classification: ClassificationCandidate,
        origin_companies: list[str],
        theme_names: list[str],
        direction: str,
        severity: str,
    ) -> str:
        clauses = [selected_classification.rule.label.lower()]
        if origin_companies:
            clauses.append(f"tracked names: {', '.join(origin_companies[:3])}")
        if theme_names:
            clauses.append(f"themes: {', '.join(theme_names[:2])}")
        clauses.append(f"{direction} / {severity}")
        return f"{headline}. {'; '.join(clauses)}."

    def _build_reasoning(
        self,
        selected_classification: ClassificationCandidate,
        mentions: list[EntityMention],
        themes: list[ThemeMatch],
        direction: str,
        direction_signals: list[str],
        severity: str,
    ) -> str:
        parts: list[str] = []
        if selected_classification.matched_keywords:
            parts.append(
                f"Matched event signals: {', '.join(selected_classification.matched_keywords[:5])}"
            )
        if mentions:
            companies = ", ".join(mention.company.ticker for mention in mentions[:4])
            parts.append(f"Tracked companies mentioned: {companies}")
        if themes:
            theme_labels = ", ".join(theme.theme_name for theme in themes[:3])
            parts.append(f"Mapped themes: {theme_labels}")
        if direction_signals:
            parts.append(f"{direction.title()} language from: {', '.join(direction_signals[:4])}")
        parts.append(f"Severity assessed as {severity}")
        return ". ".join(parts) + "."

    def _load_company_contexts(self) -> list[CompanyContext]:
        payload = load_yaml(self.settings.configs_dir / "universe.yaml")
        companies = [UniverseCompanyConfig(**item) for item in payload["companies"]]
        contexts = [
            CompanyContext(
                ticker=company.ticker,
                entity_id=f"company:{company.ticker}",
                company_name=company.company_name,
                segment_primary=company.segment_primary,
                segment_secondary=company.segment_secondary,
                aliases=self._build_company_aliases(company),
            )
            for company in companies
        ]
        return sorted(contexts, key=lambda item: item.ticker)

    def _load_theme_names(self) -> dict[str, str]:
        payload = load_yaml(self.settings.configs_dir / "theme_nodes.yaml")
        themes = [ThemeNodeRecord(**item) for item in payload["themes"]]
        return {theme.node_id: theme.theme_name for theme in themes}

    def _load_company_theme_edges(self) -> dict[str, list[RelationshipEdgeRecord]]:
        payload = load_yaml(self.settings.configs_dir / "relationship_edges.yaml")
        edges = [RelationshipEdgeRecord(**item) for item in payload["edges"]]
        mapping: dict[str, list[RelationshipEdgeRecord]] = defaultdict(list)
        for edge in edges:
            if edge.source_type != "company" or edge.target_type != "theme":
                continue
            ticker = edge.source_id.removeprefix("company:")
            mapping[ticker].append(edge)
        return mapping

    def _build_company_aliases(self, company: UniverseCompanyConfig) -> list[AliasPattern]:
        aliases: set[tuple[str, bool]] = set()

        def add_alias(value: str, *, case_sensitive: bool = False) -> None:
            normalized = _normalize_text(value)
            if not normalized:
                return
            aliases.add((value.strip(), case_sensitive))

        add_alias(company.company_name)

        ticker_is_ambiguous = len(company.ticker) <= 2 or company.ticker.lower() in {"on"}
        add_alias(company.ticker, case_sensitive=ticker_is_ambiguous)

        cleaned_words = [word for word in re.findall(r"[A-Za-z0-9]+", company.company_name)]
        while cleaned_words and cleaned_words[-1].lower() in LEGAL_SUFFIXES:
            cleaned_words.pop()
        if cleaned_words:
            add_alias(" ".join(cleaned_words))
        if len(cleaned_words) >= 2:
            add_alias(" ".join(cleaned_words[:2]))
        acronym = "".join(word[0] for word in cleaned_words if word)
        if 3 <= len(acronym) <= 5:
            add_alias(acronym, case_sensitive=False)
        first_word = cleaned_words[0].lower() if cleaned_words else ""
        if first_word and first_word not in GENERIC_SINGLE_WORD_ALIASES and len(first_word) > 4:
            add_alias(first_word)
        for alias in MANUAL_COMPANY_ALIASES.get(company.ticker, []):
            add_alias(alias)

        patterns = [
            AliasPattern(
                phrase=value,
                normalized_phrase=_normalize_text(value),
                case_sensitive=case_sensitive,
            )
            for value, case_sensitive in aliases
        ]
        patterns.sort(key=lambda item: (-len(item.normalized_phrase), item.phrase.lower()))
        return patterns


def _collect_hits(article: ArticleContext, phrases: list[str]) -> list[str]:
    hits: list[str] = []
    for phrase in phrases:
        if _count_normalized_phrase(article.title_text, phrase) or _count_normalized_phrase(article.full_text, phrase):
            hits.append(phrase)
    return hits


def _count_alias_matches(normalized_text: str, raw_text: str, alias: AliasPattern) -> int:
    if alias.case_sensitive:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(alias.phrase)}(?![A-Za-z0-9])"
        return len(re.findall(pattern, raw_text))
    return _count_normalized_phrase(normalized_text, alias.normalized_phrase)


def _count_normalized_phrase(text: str, phrase: str) -> int:
    normalized_phrase = _normalize_text(phrase)
    if not normalized_phrase:
        return 0
    pattern = rf"(?<![a-z0-9]){re.escape(normalized_phrase)}(?![a-z0-9])"
    return len(re.findall(pattern, text))


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def _coerce_optional_str(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _coerce_optional_datetime(value: object) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    timestamp = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(timestamp):
        return None
    return timestamp.to_pydatetime()


def _domain_from_url(value: str | None) -> str:
    if not value:
        return "unknown"
    parsed = urlparse(value)
    return (parsed.netloc or value).lower().removeprefix("www.")
