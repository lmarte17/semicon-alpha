from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any

import pandas as pd

from semicon_alpha.models.records import EventLagPredictionRecord, LagProfileRecord
from semicon_alpha.scoring.rules import ScoringRules, load_scoring_rules, ordered_lag_buckets
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import ensure_dir, now_utc, records_to_dataframe, upsert_parquet


class LagModelingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.events_path = settings.processed_dir / "news_events_structured.parquet"
        self.influence_path = settings.processed_dir / "event_node_influence.parquet"
        self.company_registry_path = settings.processed_dir / "company_registry.parquet"
        self.evaluation_path = settings.processed_dir / "event_market_reactions.parquet"
        self.lag_profiles_path = settings.processed_dir / "lag_profiles.parquet"
        self.predictions_path = settings.processed_dir / "event_lag_predictions.parquet"
        self.rules_path = settings.configs_dir / "scoring_rules.yaml"

    def run(self, limit: int | None = None, force: bool = False) -> dict[str, int]:
        if not self.events_path.exists() or not self.influence_path.exists():
            raise FileNotFoundError(
                "Required datasets are missing. Run `semicon-alpha event-sync` and `semicon-alpha graph-propagate` first."
            )
        if not self.company_registry_path.exists():
            raise FileNotFoundError("Company registry is missing. Run `semicon-alpha reference-sync` first.")

        events = pd.read_parquet(self.events_path)
        if events.empty:
            self._replace_parquet(self.lag_profiles_path, [], LagProfileRecord)
            self._replace_parquet(self.predictions_path, [], EventLagPredictionRecord)
            self.catalog.refresh_processed_views()
            return {"profile_count": 0, "prediction_count": 0, "event_count": 0}

        if not force and self.predictions_path.exists():
            existing = pd.read_parquet(self.predictions_path, columns=["event_id"])
            existing_event_ids = set(existing["event_id"].tolist())
            if existing_event_ids:
                events = events[~events["event_id"].isin(existing_event_ids)]

        if limit is not None:
            events = events.head(limit)
        if events.empty:
            return {"profile_count": 0, "prediction_count": 0, "event_count": 0}

        rules = load_scoring_rules(self.rules_path)
        company_frame = pd.read_parquet(self.company_registry_path)
        influence_frame = pd.read_parquet(self.influence_path)
        influence_frame = influence_frame[influence_frame["node_type"] == "company"].copy()
        influence_frame["ticker"] = influence_frame["node_id"].map(_ticker_from_entity_id)
        influence_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in influence_frame.to_dict(orient="records"):
            influence_by_event[row["event_id"]].append(row)

        evaluation_frame = _read_optional_parquet(self.evaluation_path)
        if not evaluation_frame.empty:
            evaluation_frame["published_date"] = evaluation_frame["event_published_at_utc"].map(_to_optional_date)

        company_by_ticker = {
            row["ticker"]: row for row in company_frame.to_dict(orient="records")
        }
        processed_at = now_utc()
        lag_profiles = self._build_lag_profiles(evaluation_frame, processed_at)
        predictions: list[EventLagPredictionRecord] = []

        for event_row in events.to_dict(orient="records"):
            event_id = str(event_row["event_id"])
            event_date = _to_optional_date(event_row.get("published_at_utc"))
            event_predictions = influence_by_event.get(event_id, [])
            for influence_row in event_predictions:
                ticker = influence_row.get("ticker")
                if not ticker:
                    continue
                company_row = company_by_ticker.get(str(ticker))
                if company_row is None:
                    continue
                predictions.append(
                    self._predict_event_lag(
                        event_row=event_row,
                        influence_row=influence_row,
                        company_row=company_row,
                        evaluation_frame=evaluation_frame,
                        event_date=event_date,
                        rules=rules,
                        processed_at=processed_at,
                    )
                )

        self._replace_parquet(self.lag_profiles_path, lag_profiles, LagProfileRecord)
        upsert_parquet(
            self.predictions_path,
            predictions,
            unique_keys=["event_id", "ticker"],
            sort_by=["event_id", "ticker", "processed_at_utc"],
        )
        self.catalog.refresh_processed_views()
        return {
            "profile_count": len(lag_profiles),
            "prediction_count": len(predictions),
            "event_count": len(events),
        }

    def _build_lag_profiles(
        self,
        evaluation_frame: pd.DataFrame,
        processed_at: datetime,
    ) -> list[LagProfileRecord]:
        if evaluation_frame.empty:
            return []
        valid = evaluation_frame[
            evaluation_frame["realized_lag_bucket"].notna()
            & evaluation_frame["best_signed_abnormal_return"].notna()
            & (evaluation_frame["best_signed_abnormal_return"] > 0)
        ].copy()
        if valid.empty:
            return []

        profiles: list[LagProfileRecord] = []
        scope_specs = [
            ("ticker_event_type", ["ticker", "event_type"]),
            ("segment_event_type", ["segment_primary", "event_type"]),
            ("role_event_type", ["ecosystem_role", "event_type"]),
        ]
        for scope_type, columns in scope_specs:
            subset = valid.dropna(subset=columns)
            if subset.empty:
                continue
            for keys, group in subset.groupby(columns):
                if not isinstance(keys, tuple):
                    keys = (keys,)
                scope_key = str(keys[0])
                event_type = str(keys[1])
                distribution = _bucket_distribution_from_rows(group.to_dict(orient="records"))
                if not distribution:
                    continue
                preferred_bucket = max(distribution, key=distribution.get)
                sample_size = len(group)
                confidence = _clamp(0.25 + sample_size * 0.07, 0.1, 0.95)
                profiles.append(
                    LagProfileRecord(
                        scope_type=scope_type,
                        scope_key=scope_key,
                        event_type=event_type,
                        sample_size=sample_size,
                        preferred_lag_bucket=preferred_bucket,
                        lag_bucket_scores=distribution,
                        mean_signed_abnormal_return=round(
                            float(group["best_signed_abnormal_return"].mean()), 4
                        ),
                        confidence=round(confidence, 4),
                        computed_at_utc=processed_at,
                    )
                )
        return profiles

    def _predict_event_lag(
        self,
        event_row: dict[str, Any],
        influence_row: dict[str, Any],
        company_row: dict[str, Any],
        evaluation_frame: pd.DataFrame,
        event_date: date | None,
        rules: ScoringRules,
        processed_at: datetime,
    ) -> EventLagPredictionRecord:
        ticker = str(company_row["ticker"])
        direct_exposure = float(influence_row.get("direct_path_score", 0.0) or 0.0)
        second_order = float(influence_row.get("second_order_score", 0.0) or 0.0)
        third_order = float(influence_row.get("third_order_score", 0.0) or 0.0)
        aggregate_score = float(influence_row.get("aggregate_influence_score", 0.0) or 0.0)
        best_hop_count = int(influence_row.get("best_hop_count", 0) or 0)
        impact_direction = str(influence_row.get("provisional_direction") or event_row["direction"])
        origin_companies = set(_parse_json_list(event_row.get("origin_companies")))
        mentioned_companies = set(_parse_json_list(event_row.get("mentioned_companies")))

        is_origin = ticker in origin_companies
        is_mentioned = ticker in mentioned_companies
        non_obviousness = _compute_non_obviousness(
            direct_exposure=direct_exposure,
            second_order=second_order,
            third_order=third_order,
            is_origin=is_origin,
            is_mentioned=is_mentioned,
        )

        lag_rules = rules.lag_heuristics
        market_cap_bucket = _coerce_optional_str(company_row.get("market_cap_bucket"))
        ecosystem_role = _coerce_optional_str(company_row.get("ecosystem_role"))
        heuristic_center = lag_rules.base_center
        heuristic_center -= direct_exposure * lag_rules.direct_exposure_drag
        heuristic_center += second_order * lag_rules.second_order_shift
        heuristic_center += third_order * lag_rules.third_order_shift
        heuristic_center += non_obviousness * lag_rules.non_obvious_shift
        heuristic_center += lag_rules.market_cap_shifts.get(str(market_cap_bucket), 0.0)
        heuristic_center += lag_rules.ecosystem_role_shifts.get(str(ecosystem_role), 0.0)

        ordered_buckets = ordered_lag_buckets(rules)
        max_index = max(len(ordered_buckets) - 1, 0)
        heuristic_center = _clamp(heuristic_center, 0.0, float(max_index))
        heuristic_distribution = _distribution_from_center(heuristic_center, ordered_buckets)
        empirical_distribution, empirical_support_count, empirical_reason_codes = _lookup_empirical_distribution(
            evaluation_frame=evaluation_frame,
            event_row=event_row,
            company_row=company_row,
            event_date=event_date,
            rules=rules,
        )
        blended_distribution = dict(heuristic_distribution)
        for bucket_name, score in empirical_distribution.items():
            blended_distribution[bucket_name] = blended_distribution.get(bucket_name, 0.0) + score
        blended_distribution = _normalize_distribution(blended_distribution)

        predicted_lag_bucket = max(blended_distribution, key=blended_distribution.get)
        delayed_probability = 1.0 - blended_distribution.get("same_day", 0.0)
        delayed_reaction_score = _clamp(
            aggregate_score * delayed_probability * (0.6 + 0.4 * non_obviousness),
            0.0,
            0.99,
        )
        distribution_values = sorted(blended_distribution.values(), reverse=True)
        confidence_gap = distribution_values[0] - distribution_values[1] if len(distribution_values) > 1 else distribution_values[0]
        lag_confidence = _clamp(
            0.35 + confidence_gap * 0.45 + min(empirical_support_count, 5) * 0.04,
            0.1,
            0.99,
        )

        lag_reason_codes = [
            f"lag_bucket:{predicted_lag_bucket}",
            f"best_hop_count:{best_hop_count}",
        ]
        if second_order > 0:
            lag_reason_codes.append("lag_driver:second_order_exposure")
        if third_order > 0:
            lag_reason_codes.append("lag_driver:third_order_exposure")
        if non_obviousness >= 0.5:
            lag_reason_codes.append("lag_driver:non_obvious")
        if market_cap_bucket:
            lag_reason_codes.append(f"market_cap:{market_cap_bucket}")
        if ecosystem_role:
            lag_reason_codes.append(f"ecosystem_role:{ecosystem_role}")
        lag_reason_codes.extend(empirical_reason_codes)

        reasoning = (
            f"{ticker} is modeled for a {predicted_lag_bucket} reaction window with "
            f"heuristic center {heuristic_center:.2f}. Delayed-reaction score {delayed_reaction_score:.2f} "
            f"reflects hop depth, non-obviousness, and any available empirical lag support."
        )
        return EventLagPredictionRecord(
            event_id=str(event_row["event_id"]),
            ticker=ticker,
            entity_id=str(company_row["entity_id"]),
            event_type=str(event_row["event_type"]),
            impact_direction=impact_direction,
            market_cap_bucket=market_cap_bucket,
            ecosystem_role=ecosystem_role,
            best_hop_count=best_hop_count,
            heuristic_lag_center=round(heuristic_center, 4),
            predicted_lag_bucket=predicted_lag_bucket,
            lag_bucket_scores={key: round(value, 4) for key, value in blended_distribution.items()},
            delayed_reaction_score=round(delayed_reaction_score, 4),
            lag_confidence=round(lag_confidence, 4),
            empirical_support_count=empirical_support_count,
            lag_reason_codes=lag_reason_codes,
            reasoning=reasoning,
            processed_at_utc=processed_at,
        )

    def _replace_parquet(self, path, records, model_cls) -> None:
        frame = records_to_dataframe(records) if records else pd.DataFrame(columns=list(model_cls.model_fields))
        ensure_dir(path.parent)
        frame.to_parquet(path, index=False)


def _lookup_empirical_distribution(
    evaluation_frame: pd.DataFrame,
    event_row: dict[str, Any],
    company_row: dict[str, Any],
    event_date: date | None,
    rules: ScoringRules,
) -> tuple[dict[str, float], int, list[str]]:
    if evaluation_frame.empty:
        return {}, 0, []
    if event_date is not None:
        evaluation_frame = evaluation_frame[
            evaluation_frame["published_date"].notna() & (evaluation_frame["published_date"] < event_date)
        ]
    if evaluation_frame.empty:
        return {}, 0, []

    event_type = str(event_row["event_type"])
    weighted_scores: dict[str, float] = defaultdict(float)
    support_count = 0
    reason_codes: list[str] = []
    scope_specs = [
        (
            "ticker_event_type",
            (evaluation_frame["ticker"] == company_row["ticker"]) & (evaluation_frame["event_type"] == event_type),
        ),
        (
            "segment_event_type",
            evaluation_frame["segment_primary"].notna()
            & (evaluation_frame["segment_primary"] == company_row.get("segment_primary"))
            & (evaluation_frame["event_type"] == event_type),
        ),
        (
            "role_event_type",
            evaluation_frame["ecosystem_role"].notna()
            & (evaluation_frame["ecosystem_role"] == company_row.get("ecosystem_role"))
            & (evaluation_frame["event_type"] == event_type),
        ),
    ]
    for scope_type, mask in scope_specs:
        group = evaluation_frame[mask]
        if group.empty:
            continue
        distribution = _bucket_distribution_from_rows(group.to_dict(orient="records"))
        if not distribution:
            continue
        scope_weight = rules.lag_heuristics.empirical_weights.get(scope_type, 0.0)
        for bucket_name, bucket_score in distribution.items():
            weighted_scores[bucket_name] += bucket_score * scope_weight
        support_count += len(group)
        reason_codes.append(f"empirical_scope:{scope_type}")

    if not weighted_scores:
        return {}, 0, []
    return _normalize_distribution(weighted_scores), support_count, reason_codes


def _bucket_distribution_from_rows(rows: list[dict[str, Any]]) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for row in rows:
        bucket = _coerce_optional_str(row.get("realized_lag_bucket"))
        signed_abnormal = float(row.get("best_signed_abnormal_return", 0.0) or 0.0)
        if not bucket or signed_abnormal <= 0:
            continue
        scores[bucket] += signed_abnormal
    return _normalize_distribution(scores)


def _distribution_from_center(center: float, ordered_buckets: list[tuple[str, int]]) -> dict[str, float]:
    distribution: dict[str, float] = {}
    for index, (bucket_name, _offset) in enumerate(ordered_buckets):
        distribution[bucket_name] = max(0.05, 1.0 - (abs(index - center) / 2.25))
    return _normalize_distribution(distribution)


def _normalize_distribution(distribution: dict[str, float]) -> dict[str, float]:
    total = sum(max(value, 0.0) for value in distribution.values())
    if total <= 0:
        return {}
    return {key: max(value, 0.0) / total for key, value in distribution.items()}


def _compute_non_obviousness(
    direct_exposure: float,
    second_order: float,
    third_order: float,
    is_origin: bool,
    is_mentioned: bool,
) -> float:
    score = 0.0
    score += max(0.0, 0.35 - direct_exposure)
    score += second_order * 0.8
    score += third_order * 1.1
    if not is_origin:
        score += 0.2
    if not is_mentioned:
        score += 0.1
    return _clamp(score, 0.0, 1.0)


def _ticker_from_entity_id(value: str) -> str:
    return value.split(":", 1)[1] if ":" in value else value


def _read_optional_parquet(path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _parse_json_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return [item.strip() for item in text.split(",") if item.strip()]
    return [str(value)]


def _to_optional_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _coerce_optional_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
