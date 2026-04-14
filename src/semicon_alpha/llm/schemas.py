from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ArticleTriageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance_label: str = Field(
        description="One of: relevant_event, relevant_background, peripheral, not_relevant."
    )
    is_semiconductor_relevant: bool
    is_event_worthy: bool
    article_type: str = Field(
        description="Short normalized type such as policy, supply_chain, earnings, fab, regulation, demand, or commentary."
    )
    primary_subjects: list[str] = Field(default_factory=list)
    mentioned_companies: list[str] = Field(default_factory=list)
    mentioned_technologies: list[str] = Field(default_factory=list)
    mentioned_countries: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    abstain: bool = False
    needs_review: bool = False
    rejection_reason: str | None = None
    reasoning_summary: str


class EventReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_event_type: str
    selected_direction: str
    selected_severity: str
    summary: str
    reasoning_summary: str
    suggested_origin_companies: list[str] = Field(default_factory=list)
    suggested_mentioned_companies: list[str] = Field(default_factory=list)
    suggested_regulators: list[str] = Field(default_factory=list)
    suggested_countries: list[str] = Field(default_factory=list)
    suggested_technologies: list[str] = Field(default_factory=list)
    suggested_facilities: list[str] = Field(default_factory=list)
    suggested_primary_theme_ids: list[str] = Field(default_factory=list)
    suggested_secondary_theme_ids: list[str] = Field(default_factory=list)
    suggested_primary_segment: str | None = None
    suggested_secondary_segments: list[str] = Field(default_factory=list)
    time_horizon_hint: str | None = None
    evidence_spans: list[str] = Field(default_factory=list)
    uncertainty_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    abstain: bool = False
    needs_review: bool = False
    review_notes: str | None = None
