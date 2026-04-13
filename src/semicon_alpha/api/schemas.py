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


class CopilotResponse(APIBaseModel):
    answer: str
    observations: list[str]
    inferences: list[str]
    citations: list[dict[str, Any]]
    related_entities: list[dict[str, Any]]
    related_events: list[dict[str, Any]]
