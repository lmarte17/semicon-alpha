from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from semicon_alpha.utils.io import load_yaml


class ScoringBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExposureWeights(ScoringBaseModel):
    direct: float
    second_order: float
    third_order: float
    lag_profile: float
    segment_primary_match: float
    segment_secondary_match: float
    segment_overlap: float
    history_ticker_event: float
    history_segment_event: float
    history_role_event: float


class ObviousnessPenalties(ScoringBaseModel):
    origin_company_base: float
    mentioned_company_base: float
    origin_name_candidate_base: float
    direct_exposure_multiplier: float
    mega_cap_bonus: float
    large_cap_bonus: float


class LagHeuristics(ScoringBaseModel):
    base_center: float
    direct_exposure_drag: float
    second_order_shift: float
    third_order_shift: float
    non_obvious_shift: float
    market_cap_shifts: dict[str, float]
    ecosystem_role_shifts: dict[str, float]
    empirical_weights: dict[str, float]


class EvaluationConfig(ScoringBaseModel):
    minimum_move_threshold: float
    hit_thresholds: dict[str, float]
    volume_lookback_days: int
    top_n_metrics: list[int]
    non_obvious_direct_exposure_max: float


class ScoringRules(ScoringBaseModel):
    version: str
    benchmark_ticker: str
    lag_buckets: dict[str, int]
    exposure_weights: ExposureWeights
    obviousness_penalties: ObviousnessPenalties
    lag_heuristics: LagHeuristics
    evaluation: EvaluationConfig


def load_scoring_rules(path: Path) -> ScoringRules:
    return ScoringRules(**load_yaml(path))


def ordered_lag_buckets(rules: ScoringRules) -> list[tuple[str, int]]:
    return list(rules.lag_buckets.items())
