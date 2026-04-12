from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from semicon_alpha.utils.io import load_yaml


DirectionLabel = Literal["positive", "negative", "mixed", "ambiguous"]
SeverityLabel = Literal["low", "medium", "high", "critical"]


class TaxonomyBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventTypeRule(TaxonomyBaseModel):
    event_type: str
    label: str
    description: str
    keywords: list[str] = Field(default_factory=list)
    secondary_keywords: list[str] = Field(default_factory=list)
    theme_ids: list[str] = Field(default_factory=list)
    segment_hints: list[str] = Field(default_factory=list)
    default_direction: DirectionLabel = "ambiguous"
    base_severity: SeverityLabel = "medium"


class PhraseBuckets(TaxonomyBaseModel):
    positive: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    mixed: list[str] = Field(default_factory=list)


class SeverityBuckets(TaxonomyBaseModel):
    critical: list[str] = Field(default_factory=list)
    high: list[str] = Field(default_factory=list)
    medium: list[str] = Field(default_factory=list)


class EventTaxonomy(TaxonomyBaseModel):
    version: str
    semiconductor_keywords: list[str] = Field(default_factory=list)
    direction_keywords: PhraseBuckets
    severity_keywords: SeverityBuckets
    event_types: list[EventTypeRule]


def load_event_taxonomy(path: Path) -> EventTaxonomy:
    payload = load_yaml(path)
    return EventTaxonomy(**payload)
