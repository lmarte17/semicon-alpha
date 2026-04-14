from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class APIBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchResult(APIBaseModel):
    id: str
    type: str
    title: str
    subtitle: str | None = None
    url: str | None = None
    score: float | None = None


class DashboardOverview(APIBaseModel):
    metrics: dict[str, Any]
    recent_events: list[dict[str, Any]]
    top_non_obvious_impacts: list[dict[str, Any]]


class EventWorkspace(APIBaseModel):
    event: dict[str, Any]
    impact_candidates: list[dict[str, Any]]
    propagation_paths: list[dict[str, Any]]
    themes: list[dict[str, Any]]
    supporting_evidence: dict[str, Any]
    competing_interpretations: list[dict[str, Any]]
    historical_analogs: list[dict[str, Any]]


class EntityWorkspace(APIBaseModel):
    entity: dict[str, Any]
    neighbors: dict[str, Any]
    recent_events: list[dict[str, Any]]
    exposure_summary: dict[str, Any]
    effect_pathways: list[dict[str, Any]]
    evidence: dict[str, Any]
    history: list[dict[str, Any]]


class SearchResponse(APIBaseModel):
    entities: list[SearchResult]
    events: list[SearchResult]
    documents: list[SearchResult]
    themes: list[SearchResult]


class PathTraceRequest(APIBaseModel):
    source_id: str
    target_id: str
    max_hops: int = Field(default=4, ge=1, le=6)
    relationship_types: list[str] | None = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    max_paths: int = Field(default=5, ge=1, le=20)


class PathTraceResponse(APIBaseModel):
    source_id: str
    target_id: str
    source_label: str
    target_label: str
    paths: list[dict[str, Any]]


class CopilotQueryRequest(APIBaseModel):
    query: str
    event_id: str | None = None
    entity_id: str | None = None
    scenario_id: str | None = None
    thesis_id: str | None = None


class CopilotResponse(APIBaseModel):
    answer: str
    observations: list[str]
    inferences: list[str]
    uncertainties: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]]
    related_entities: list[dict[str, Any]]
    related_events: list[dict[str, Any]]


class CreateWatchlistRequest(APIBaseModel):
    name: str
    description: str | None = None


class AddWatchlistItemRequest(APIBaseModel):
    item_type: str
    item_id: str
    label: str | None = None
    metadata: dict[str, Any] | None = None


class WatchlistWorkspace(APIBaseModel):
    watchlist: dict[str, Any]
    items: list[dict[str, Any]]
    event_feed: list[dict[str, Any]]
    alerts: list[dict[str, Any]]


class CreateBoardRequest(APIBaseModel):
    name: str
    description: str | None = None
    layout: dict[str, Any] | None = None


class AddBoardItemRequest(APIBaseModel):
    item_type: str
    item_id: str | None = None
    title: str | None = None
    content: str | None = None
    position: dict[str, Any] | None = None


class BoardWorkspace(APIBaseModel):
    board: dict[str, Any]
    items: list[dict[str, Any]]
    notes: list[dict[str, Any]]
    reports: list[dict[str, Any]]
    event_feed: list[dict[str, Any]]
    alerts: list[dict[str, Any]]


class CreateNoteRequest(APIBaseModel):
    subject_type: str
    subject_id: str
    body: str
    title: str | None = None
    stance: str | None = None
    board_id: str | None = None


class CreateSavedQueryRequest(APIBaseModel):
    name: str
    query_text: str
    query_type: str = "global_search"
    filters: dict[str, Any] | None = None


class RunSavedQueryResponse(APIBaseModel):
    saved_query: dict[str, Any]
    results: dict[str, list[dict[str, Any]]]


class AlertListResponse(APIBaseModel):
    alerts: list[dict[str, Any]]


class EventBacktestResponse(APIBaseModel):
    event: dict[str, Any]
    predicted_vs_realized: list[dict[str, Any]]
    summary: dict[str, Any]
    supporting_evidence: dict[str, Any]


class GenerateReportRequest(APIBaseModel):
    report_type: str
    event_id: str | None = None
    entity_id: str | None = None
    compare_entity_id: str | None = None
    board_id: str | None = None
    scenario_id: str | None = None
    thesis_id: str | None = None
    query: str | None = None


class ScenarioAssumptionRequest(APIBaseModel):
    item_type: str
    item_id: str
    direction: str
    magnitude: str = "medium"
    confidence: float = Field(default=0.7, ge=0.05, le=1.0)
    rationale: str | None = None
    label: str | None = None


class ScenarioMonitorRequest(APIBaseModel):
    item_type: str
    item_id: str
    expected_direction: str | None = None
    label: str | None = None
    threshold: dict[str, Any] | None = None


class CreateScenarioRequest(APIBaseModel):
    name: str
    description: str | None = None
    summary: str | None = None
    status: str = "active"
    assumptions: list[ScenarioAssumptionRequest]
    monitors: list[ScenarioMonitorRequest] | None = None


class ScenarioWorkspace(APIBaseModel):
    scenario: dict[str, Any]
    assumptions: list[dict[str, Any]]
    monitors: list[dict[str, Any]]
    latest_run: dict[str, Any] | None = None
    run_history: list[dict[str, Any]]
    support_signals: list[dict[str, Any]]
    contradiction_signals: list[dict[str, Any]]
    alerts: list[dict[str, Any]]


class ThesisLinkRequest(APIBaseModel):
    item_type: str
    item_id: str
    relationship: str = "supports"
    label: str | None = None
    metadata: dict[str, Any] | None = None


class CreateThesisRequest(APIBaseModel):
    title: str
    statement: str
    stance: str = "mixed"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: str = "active"
    time_horizon: str | None = None
    links: list[ThesisLinkRequest] | None = None
    initial_update: str | None = None


class ThesisUpdateRequest(APIBaseModel):
    summary: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ThesisWorkspace(APIBaseModel):
    thesis: dict[str, Any]
    links: list[dict[str, Any]]
    updates: list[dict[str, Any]]
    support_signals: list[dict[str, Any]]
    contradiction_signals: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
