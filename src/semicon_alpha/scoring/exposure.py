from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import pandas as pd

from semicon_alpha.models.records import EventImpactScoreRecord
from semicon_alpha.scoring.rules import ScoringRules, load_scoring_rules
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, upsert_parquet


class ExposureScoringService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.events_path = settings.processed_dir / "news_events_structured.parquet"
        self.influence_path = settings.processed_dir / "event_node_influence.parquet"
        self.company_registry_path = settings.processed_dir / "company_registry.parquet"
        self.lag_predictions_path = settings.processed_dir / "event_lag_predictions.parquet"
        self.evaluation_path = settings.processed_dir / "event_market_reactions.parquet"
        self.scores_path = settings.processed_dir / "event_impact_scores.parquet"
        self.rules_path = settings.configs_dir / "scoring_rules.yaml"

    def run(self, limit: int | None = None, force: bool = False) -> dict[str, int]:
        required_paths = [
            self.events_path,
            self.influence_path,
            self.company_registry_path,
            self.lag_predictions_path,
        ]
        missing = [str(path) for path in required_paths if not path.exists()]
        if missing:
            raise FileNotFoundError(
                "Required datasets are missing. Run `semicon-alpha lag-sync` after the event and graph steps first."
            )

        events = pd.read_parquet(self.events_path)
        if events.empty:
            return {"event_count": 0, "score_count": 0}

        if not force and self.scores_path.exists():
            existing = pd.read_parquet(self.scores_path, columns=["event_id"])
            existing_event_ids = set(existing["event_id"].tolist())
            if existing_event_ids:
                events = events[~events["event_id"].isin(existing_event_ids)]

        if limit is not None:
            events = events.head(limit)
        if events.empty:
            return {"event_count": 0, "score_count": 0}

        rules = load_scoring_rules(self.rules_path)
        influence_frame = pd.read_parquet(self.influence_path)
        influence_frame = influence_frame[influence_frame["node_type"] == "company"].copy()
        influence_frame["ticker"] = influence_frame["node_id"].map(_ticker_from_entity_id)
        lag_frame = pd.read_parquet(self.lag_predictions_path)
        evaluation_frame = _read_optional_parquet(self.evaluation_path)
        if not evaluation_frame.empty:
            evaluation_frame["published_date"] = evaluation_frame["event_published_at_utc"].map(_to_optional_date)

        company_frame = pd.read_parquet(self.company_registry_path)
        company_by_ticker = {
            row["ticker"]: row for row in company_frame.to_dict(orient="records")
        }
        lag_by_key = {
            (row["event_id"], row["ticker"]): row for row in lag_frame.to_dict(orient="records")
        }
        event_rows = {row["event_id"]: row for row in events.to_dict(orient="records")}

        scores: list[EventImpactScoreRecord] = []
        processed_at = now_utc()
        for influence_row in influence_frame.to_dict(orient="records"):
            event_row = event_rows.get(influence_row["event_id"])
            if event_row is None:
                continue
            ticker = str(influence_row["ticker"])
            company_row = company_by_ticker.get(ticker)
            lag_row = lag_by_key.get((str(event_row["event_id"]), ticker))
            if company_row is None or lag_row is None:
                continue
            scores.append(
                self._score_company_impact(
                    event_row=event_row,
                    influence_row=influence_row,
                    lag_row=lag_row,
                    company_row=company_row,
                    evaluation_frame=evaluation_frame,
                    rules=rules,
                    processed_at=processed_at,
                )
            )

        upsert_parquet(
            self.scores_path,
            scores,
            unique_keys=["event_id", "ticker"],
            sort_by=["event_id", "ticker", "processed_at_utc"],
        )
        self.catalog.refresh_processed_views()
        return {"event_count": len(events), "score_count": len(scores)}

    def _score_company_impact(
        self,
        event_row: dict[str, Any],
        influence_row: dict[str, Any],
        lag_row: dict[str, Any],
        company_row: dict[str, Any],
        evaluation_frame: pd.DataFrame,
        rules: ScoringRules,
        processed_at: datetime,
    ) -> EventImpactScoreRecord:
        weights = rules.exposure_weights
        penalties = rules.obviousness_penalties
        ticker = str(company_row["ticker"])
        event_id = str(event_row["event_id"])
        direct_exposure = float(
            max(
                float(influence_row.get("direct_path_score", 0.0) or 0.0),
                float(influence_row.get("first_order_score", 0.0) or 0.0),
            )
        )
        second_order = float(influence_row.get("second_order_score", 0.0) or 0.0)
        third_order = float(influence_row.get("third_order_score", 0.0) or 0.0)
        structural_exposure = (
            direct_exposure * weights.direct
            + second_order * weights.second_order
            + third_order * weights.third_order
        )

        origin_companies = set(_parse_json_list(event_row.get("origin_companies")))
        mentioned_companies = set(_parse_json_list(event_row.get("mentioned_companies")))
        is_origin_company = ticker in origin_companies
        is_mentioned_company = ticker in mentioned_companies
        segment_score, segment_reason_codes = _compute_segment_exposure(
            event_row=event_row,
            company_row=company_row,
            rules=rules,
        )
        history_score, history_support_count, history_confidence, history_reason_codes = _compute_historical_similarity(
            evaluation_frame=evaluation_frame,
            event_row=event_row,
            company_row=company_row,
            rules=rules,
        )
        delayed_reaction_score = float(lag_row.get("delayed_reaction_score", 0.0) or 0.0) * weights.lag_profile

        obviousness_penalty = 0.0
        if is_origin_company:
            obviousness_penalty += penalties.origin_company_base
        elif is_mentioned_company:
            obviousness_penalty += penalties.mentioned_company_base
        elif bool(company_row.get("is_origin_name_candidate")):
            obviousness_penalty += penalties.origin_name_candidate_base
        obviousness_penalty += direct_exposure * penalties.direct_exposure_multiplier
        market_cap_bucket = _coerce_optional_str(company_row.get("market_cap_bucket"))
        if market_cap_bucket == "mega":
            obviousness_penalty += penalties.mega_cap_bonus
        elif market_cap_bucket == "large":
            obviousness_penalty += penalties.large_cap_bonus

        total_rank_score = max(
            0.0,
            structural_exposure + segment_score + history_score + delayed_reaction_score - obviousness_penalty,
        )
        lag_confidence = float(lag_row.get("lag_confidence", 0.0) or 0.0)
        influence_confidence = float(influence_row.get("confidence", 0.0) or 0.0)
        confidence = _clamp(
            influence_confidence * 0.55 + lag_confidence * 0.30 + history_confidence * 0.15,
            0.05,
            0.99,
        )
        is_non_obvious = (
            not is_origin_company
            and not is_mentioned_company
            and (
                int(influence_row.get("best_hop_count", 0) or 0) >= 2
                or direct_exposure <= rules.evaluation.non_obvious_direct_exposure_max
            )
        )
        top_paths = _parse_json_value(influence_row.get("top_paths"), [])
        impact_direction = str(influence_row.get("provisional_direction") or event_row["direction"])
        predicted_lag_bucket = str(lag_row["predicted_lag_bucket"])

        reason_codes = [
            f"impact_direction:{impact_direction}",
            f"lag_bucket:{predicted_lag_bucket}",
        ]
        reason_codes.extend(segment_reason_codes)
        reason_codes.extend(history_reason_codes)
        reason_codes.extend(_parse_json_list(lag_row.get("lag_reason_codes")))
        if is_origin_company:
            reason_codes.append("obviousness:origin_company")
        elif is_mentioned_company:
            reason_codes.append("obviousness:mentioned_company")
        elif bool(company_row.get("is_origin_name_candidate")):
            reason_codes.append("obviousness:origin_name_candidate")
        if is_non_obvious:
            reason_codes.append("screen:non_obvious")

        explanation = _build_explanation(
            ticker=ticker,
            event_type=str(event_row["event_type"]),
            direction=impact_direction,
            predicted_lag_bucket=predicted_lag_bucket,
            structural_exposure=structural_exposure,
            segment_score=segment_score,
            history_score=history_score,
            delayed_reaction_score=delayed_reaction_score,
            obviousness_penalty=obviousness_penalty,
            top_paths=top_paths,
        )
        return EventImpactScoreRecord(
            event_id=event_id,
            ticker=ticker,
            entity_id=str(company_row["entity_id"]),
            event_type=str(event_row["event_type"]),
            published_at_utc=_to_optional_datetime(event_row.get("published_at_utc")),
            impact_direction=impact_direction,
            best_hop_count=int(influence_row.get("best_hop_count", 0) or 0),
            direct_exposure_score=round(direct_exposure, 4),
            second_order_score=round(second_order, 4),
            third_order_score=round(third_order, 4),
            structural_exposure_score=round(structural_exposure, 4),
            segment_exposure_score=round(segment_score, 4),
            historical_similarity_score=round(history_score, 4),
            delayed_reaction_score=round(delayed_reaction_score, 4),
            obviousness_penalty=round(obviousness_penalty, 4),
            total_rank_score=round(total_rank_score, 4),
            confidence=round(confidence, 4),
            predicted_lag_bucket=predicted_lag_bucket,
            lag_confidence=round(lag_confidence, 4),
            historical_support_count=history_support_count,
            is_origin_company=is_origin_company,
            is_mentioned_company=is_mentioned_company,
            is_non_obvious=is_non_obvious,
            market_cap_bucket=market_cap_bucket,
            ecosystem_role=_coerce_optional_str(company_row.get("ecosystem_role")),
            primary_segment=_coerce_optional_str(company_row.get("segment_primary")),
            explanation=explanation,
            reason_codes=reason_codes,
            top_paths=top_paths if isinstance(top_paths, list) else [],
            processed_at_utc=processed_at,
        )


def _compute_segment_exposure(
    event_row: dict[str, Any],
    company_row: dict[str, Any],
    rules: ScoringRules,
) -> tuple[float, list[str]]:
    weights = rules.exposure_weights
    company_primary = _coerce_optional_str(company_row.get("segment_primary"))
    company_secondary = set(_parse_json_list(company_row.get("segment_secondary")))
    event_primary = _coerce_optional_str(event_row.get("primary_segment"))
    event_secondary = set(_parse_json_list(event_row.get("secondary_segments")))
    score = 0.0
    reason_codes: list[str] = []
    if company_primary and event_primary and company_primary == event_primary:
        score += weights.segment_primary_match
        reason_codes.append("segment_match:primary")
    if event_primary and event_primary in company_secondary:
        score += weights.segment_secondary_match
        reason_codes.append("segment_match:secondary_contains_event_primary")
    if company_primary and company_primary in event_secondary:
        score += weights.segment_secondary_match * 0.75
        reason_codes.append("segment_match:event_secondary_contains_company_primary")
    overlap = company_secondary.intersection(event_secondary)
    if overlap:
        score += min(len(overlap), 2) * weights.segment_overlap
        reason_codes.append("segment_match:secondary_overlap")
    return min(score, 0.4), reason_codes


def _compute_historical_similarity(
    evaluation_frame: pd.DataFrame,
    event_row: dict[str, Any],
    company_row: dict[str, Any],
    rules: ScoringRules,
) -> tuple[float, int, float, list[str]]:
    if evaluation_frame.empty:
        return 0.0, 0, 0.0, []
    event_date = _to_optional_date(event_row.get("published_at_utc"))
    history = evaluation_frame[evaluation_frame["published_date"].notna()].copy()
    if event_date is not None:
        history = history[history["published_date"] < event_date]
    if history.empty:
        return 0.0, 0, 0.0, []

    event_type = str(event_row["event_type"])
    positive_history = history[history["best_signed_abnormal_return"].fillna(0.0) > 0].copy()
    if positive_history.empty:
        return 0.0, 0, 0.0, []

    score = 0.0
    support_count = 0
    reason_codes: list[str] = []
    weights = rules.exposure_weights

    ticker_rows = positive_history[
        (positive_history["ticker"] == company_row["ticker"]) & (positive_history["event_type"] == event_type)
    ]
    if not ticker_rows.empty:
        score += min(
            weights.history_ticker_event,
            float(ticker_rows["best_signed_abnormal_return"].mean()) * 3.0,
        )
        support_count += len(ticker_rows)
        reason_codes.append("historical_scope:ticker_event_type")

    segment_primary = company_row.get("segment_primary")
    segment_rows = positive_history[
        positive_history["segment_primary"].notna()
        & (positive_history["segment_primary"] == segment_primary)
        & (positive_history["event_type"] == event_type)
    ]
    if not segment_rows.empty:
        score += min(
            weights.history_segment_event,
            float(segment_rows["best_signed_abnormal_return"].mean()) * 2.0,
        )
        support_count += len(segment_rows)
        reason_codes.append("historical_scope:segment_event_type")

    role_rows = positive_history[
        positive_history["ecosystem_role"].notna()
        & (positive_history["ecosystem_role"] == company_row.get("ecosystem_role"))
        & (positive_history["event_type"] == event_type)
    ]
    if not role_rows.empty:
        score += min(
            weights.history_role_event,
            float(role_rows["best_signed_abnormal_return"].mean()) * 1.5,
        )
        support_count += len(role_rows)
        reason_codes.append("historical_scope:role_event_type")

    confidence = _clamp(0.2 + support_count * 0.05, 0.0, 0.95)
    return round(score, 4), support_count, round(confidence, 4), reason_codes


def _build_explanation(
    ticker: str,
    event_type: str,
    direction: str,
    predicted_lag_bucket: str,
    structural_exposure: float,
    segment_score: float,
    history_score: float,
    delayed_reaction_score: float,
    obviousness_penalty: float,
    top_paths: Any,
) -> str:
    path_text = "no explicit path retained"
    if isinstance(top_paths, list) and top_paths:
        first_path = top_paths[0]
        nodes = first_path.get("path_nodes", [])
        if isinstance(nodes, list) and nodes:
            path_text = " -> ".join(_label_node(node) for node in nodes[:4])
    return (
        f"{ticker} screens {direction} for {event_type} with expected lag {predicted_lag_bucket}. "
        f"Structural {structural_exposure:.2f}, segment {segment_score:.2f}, history {history_score:.2f}, "
        f"delayed-reaction {delayed_reaction_score:.2f}, obviousness penalty {obviousness_penalty:.2f}. "
        f"Best path: {path_text}."
    )


def _label_node(node_id: str) -> str:
    if ":" not in node_id:
        return node_id
    prefix, value = node_id.split(":", 1)
    if prefix == "company":
        return value
    return value.replace("_", " ")


def _parse_json_value(value, default):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, (list, dict)):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _parse_json_list(value) -> list[str]:
    parsed = _parse_json_value(value, None)
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    if parsed is None:
        text = str(value).strip() if value is not None else ""
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]
    return [str(parsed)]


def _ticker_from_entity_id(value: str) -> str:
    return value.split(":", 1)[1] if ":" in value else value


def _read_optional_parquet(path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


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


def _to_optional_datetime(value) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _coerce_optional_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
