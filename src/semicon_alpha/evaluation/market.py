from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from semicon_alpha.models.records import EventMarketReactionRecord, EvaluationSummaryRecord
from semicon_alpha.scoring.rules import ScoringRules, load_scoring_rules, ordered_lag_buckets
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import ensure_dir, now_utc, records_to_dataframe, upsert_parquet


@dataclass
class PricePoint:
    trade_date: date
    price: float
    volume: float | None


class MarketEvaluationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.score_path = settings.processed_dir / "event_impact_scores.parquet"
        self.market_price_path = settings.processed_dir / "market_prices_daily.parquet"
        self.benchmark_price_path = settings.processed_dir / "benchmark_prices_daily.parquet"
        self.evaluation_path = settings.processed_dir / "event_market_reactions.parquet"
        self.summary_path = settings.processed_dir / "evaluation_summary.parquet"
        self.rules_path = settings.configs_dir / "scoring_rules.yaml"

    def run(self, limit: int | None = None, force: bool = False) -> dict[str, int]:
        required = [self.score_path, self.market_price_path, self.benchmark_price_path]
        if any(not path.exists() for path in required):
            raise FileNotFoundError(
                "Required datasets are missing. Run `semicon-alpha score-sync` and `semicon-alpha market-sync` first."
            )

        scores = pd.read_parquet(self.score_path)
        if scores.empty:
            self._replace_parquet(self.summary_path, [], EvaluationSummaryRecord)
            return {"event_count": 0, "reaction_count": 0, "summary_count": 0}

        if not force and self.evaluation_path.exists():
            existing = pd.read_parquet(self.evaluation_path, columns=["event_id"])
            existing_event_ids = set(existing["event_id"].tolist())
            if existing_event_ids:
                scores = scores[~scores["event_id"].isin(existing_event_ids)]

        if limit is not None:
            event_ids = list(dict.fromkeys(scores["event_id"].tolist()))[:limit]
            scores = scores[scores["event_id"].isin(event_ids)]
        if scores.empty:
            return {"event_count": 0, "reaction_count": 0, "summary_count": 0}

        rules = load_scoring_rules(self.rules_path)
        market_frame = pd.read_parquet(self.market_price_path)
        benchmark_frame = pd.read_parquet(self.benchmark_price_path)
        market_series = _build_price_series(market_frame)
        benchmark_series = _build_price_series(benchmark_frame)
        benchmark_ticker = _resolve_benchmark_ticker(rules, benchmark_series)
        if benchmark_ticker is None:
            raise FileNotFoundError("No benchmark price series is available for evaluation.")

        processed_at = now_utc()
        evaluations: list[EventMarketReactionRecord] = []
        for score_row in scores.to_dict(orient="records"):
            evaluations.append(
                self._evaluate_prediction(
                    score_row=score_row,
                    benchmark_ticker=benchmark_ticker,
                    market_series=market_series,
                    benchmark_series=benchmark_series[benchmark_ticker],
                    rules=rules,
                    processed_at=processed_at,
                )
            )

        evaluations = _apply_realized_move_ranks(evaluations, rules)
        upsert_parquet(
            self.evaluation_path,
            evaluations,
            unique_keys=["event_id", "ticker"],
            sort_by=["event_id", "ticker", "evaluated_at_utc"],
        )

        all_evaluations = pd.read_parquet(self.evaluation_path)
        summary_records = _build_summary_records(all_evaluations, rules, processed_at)
        self._replace_parquet(self.summary_path, summary_records, EvaluationSummaryRecord)
        self.catalog.refresh_processed_views()
        return {
            "event_count": len(set(scores["event_id"].tolist())),
            "reaction_count": len(evaluations),
            "summary_count": len(summary_records),
        }

    def _evaluate_prediction(
        self,
        score_row: dict[str, Any],
        benchmark_ticker: str,
        market_series: dict[str, list[PricePoint]],
        benchmark_series: list[PricePoint],
        rules: ScoringRules,
        processed_at: datetime,
    ) -> EventMarketReactionRecord:
        ticker = str(score_row["ticker"])
        company_series = market_series.get(ticker, [])
        published_date = _to_optional_date(score_row.get("published_at_utc"))
        anchor_index = _find_anchor_index(company_series, published_date)
        benchmark_anchor_index = _find_anchor_index(benchmark_series, published_date)

        raw_returns: dict[str, float | None] = {}
        abnormal_returns: dict[str, float | None] = {}
        abnormal_volumes: dict[str, float | None] = {}
        ordered_windows = ordered_lag_buckets(rules)
        anchor_trade_date = company_series[anchor_index].trade_date if anchor_index is not None else None

        for bucket_name, bucket_offset in ordered_windows:
            company_return = _window_return(company_series, anchor_index, bucket_offset)
            benchmark_return = _window_return(benchmark_series, benchmark_anchor_index, bucket_offset)
            raw_returns[bucket_name] = company_return
            abnormal_returns[bucket_name] = (
                company_return - benchmark_return
                if company_return is not None and benchmark_return is not None
                else None
            )
            abnormal_volumes[bucket_name] = _abnormal_volume(
                company_series,
                anchor_index,
                bucket_offset,
                rules.evaluation.volume_lookback_days,
            )

        predicted_direction = str(score_row["impact_direction"])
        predicted_lag_bucket = str(score_row["predicted_lag_bucket"])
        realized_lag_bucket = _realized_lag_bucket(abnormal_returns, predicted_direction, rules)
        best_signed_abnormal = _best_signed_abnormal_return(abnormal_returns, predicted_direction)
        realized_direction = _realized_direction(abnormal_returns, rules)
        hit_flag = _hit_flag(abnormal_returns, predicted_direction, predicted_lag_bucket, rules)
        peak_abnormal_volume = _peak_value(list(abnormal_volumes.values()))

        return EventMarketReactionRecord(
            event_id=str(score_row["event_id"]),
            ticker=ticker,
            entity_id=str(score_row["entity_id"]),
            event_type=str(score_row["event_type"]),
            event_published_at_utc=_to_optional_datetime(score_row.get("published_at_utc")),
            benchmark_ticker=benchmark_ticker,
            predicted_direction=predicted_direction,
            predicted_lag_bucket=predicted_lag_bucket,
            total_rank_score=round(float(score_row.get("total_rank_score", 0.0) or 0.0), 4),
            confidence=round(float(score_row.get("confidence", 0.0) or 0.0), 4),
            is_non_obvious=bool(score_row.get("is_non_obvious")),
            market_cap_bucket=_coerce_optional_str(score_row.get("market_cap_bucket")),
            ecosystem_role=_coerce_optional_str(score_row.get("ecosystem_role")),
            segment_primary=_coerce_optional_str(score_row.get("primary_segment")),
            anchor_trade_date=anchor_trade_date,
            realized_return_t0=_round_optional(raw_returns.get("same_day")),
            realized_return_t1=_round_optional(raw_returns.get("1d")),
            realized_return_t3=_round_optional(raw_returns.get("3d")),
            realized_return_t5=_round_optional(raw_returns.get("5d")),
            realized_return_t10=_round_optional(raw_returns.get("10d")),
            abnormal_return_t0=_round_optional(abnormal_returns.get("same_day")),
            abnormal_return_t1=_round_optional(abnormal_returns.get("1d")),
            abnormal_return_t3=_round_optional(abnormal_returns.get("3d")),
            abnormal_return_t5=_round_optional(abnormal_returns.get("5d")),
            abnormal_return_t10=_round_optional(abnormal_returns.get("10d")),
            abnormal_volume_t0=_round_optional(abnormal_volumes.get("same_day")),
            peak_abnormal_volume_t10=_round_optional(peak_abnormal_volume),
            realized_direction=realized_direction,
            realized_lag_bucket=realized_lag_bucket,
            best_signed_abnormal_return=_round_optional(best_signed_abnormal),
            hit_flag=hit_flag,
            rank_realized_move=None,
            evaluated_at_utc=processed_at,
        )

    def _replace_parquet(self, path, records, model_cls) -> None:
        frame = records_to_dataframe(records) if records else pd.DataFrame(columns=list(model_cls.model_fields))
        ensure_dir(path.parent)
        frame.to_parquet(path, index=False)


def _build_summary_records(
    evaluation_frame: pd.DataFrame,
    rules: ScoringRules,
    processed_at: datetime,
) -> list[EvaluationSummaryRecord]:
    if evaluation_frame.empty:
        return []

    records: list[EvaluationSummaryRecord] = []
    evaluation_frame["hit_flag"] = evaluation_frame["hit_flag"].fillna(False).astype(bool)
    evaluation_frame["best_signed_abnormal_return"] = evaluation_frame["best_signed_abnormal_return"].fillna(0.0)

    for top_n in rules.evaluation.top_n_metrics:
        selected = (
            evaluation_frame[evaluation_frame["is_non_obvious"].fillna(False)]
            .sort_values(["event_id", "total_rank_score"], ascending=[True, False])
            .groupby("event_id")
            .head(top_n)
        )
        if selected.empty:
            continue
        hit_rate = float(selected["hit_flag"].mean())
        mean_abnormal = float(selected["best_signed_abnormal_return"].mean())
        records.append(
            EvaluationSummaryRecord(
                metric_name="delayed_impact_hit_rate",
                metric_scope="non_obvious_top_n",
                top_n=top_n,
                metric_value=round(hit_rate, 4),
                sample_size=len(selected),
                computed_at_utc=processed_at,
            )
        )
        records.append(
            EvaluationSummaryRecord(
                metric_name="precision_at_n",
                metric_scope="non_obvious_top_n",
                top_n=top_n,
                metric_value=round(hit_rate, 4),
                sample_size=len(selected),
                computed_at_utc=processed_at,
            )
        )
        records.append(
            EvaluationSummaryRecord(
                metric_name="mean_best_signed_abnormal_return",
                metric_scope="non_obvious_top_n",
                top_n=top_n,
                metric_value=round(mean_abnormal, 4),
                sample_size=len(selected),
                computed_at_utc=processed_at,
            )
        )

    for predicted_lag_bucket, group in evaluation_frame.groupby("predicted_lag_bucket"):
        records.append(
            EvaluationSummaryRecord(
                metric_name="hit_rate",
                metric_scope="predicted_lag_bucket",
                group_key=str(predicted_lag_bucket),
                metric_value=round(float(group["hit_flag"].mean()), 4),
                sample_size=len(group),
                computed_at_utc=processed_at,
            )
        )

    for event_type, group in evaluation_frame.groupby("event_type"):
        records.append(
            EvaluationSummaryRecord(
                metric_name="hit_rate",
                metric_scope="event_type",
                group_key=str(event_type),
                metric_value=round(float(group["hit_flag"].mean()), 4),
                sample_size=len(group),
                computed_at_utc=processed_at,
            )
        )

    for scope_name, mask in {
        "non_obvious": evaluation_frame["is_non_obvious"].fillna(False),
        "obvious": ~evaluation_frame["is_non_obvious"].fillna(False),
    }.items():
        group = evaluation_frame[mask]
        if group.empty:
            continue
        records.append(
            EvaluationSummaryRecord(
                metric_name="hit_rate",
                metric_scope="obviousness",
                group_key=scope_name,
                metric_value=round(float(group["hit_flag"].mean()), 4),
                sample_size=len(group),
                computed_at_utc=processed_at,
            )
        )
    return records


def _apply_realized_move_ranks(
    evaluations: list[EventMarketReactionRecord],
    rules: ScoringRules,
) -> list[EventMarketReactionRecord]:
    ordered_windows = ordered_lag_buckets(rules)
    rows: dict[tuple[str, str], float] = {}
    for record in evaluations:
        bucket = record.realized_lag_bucket or record.predicted_lag_bucket
        abnormal_value = _abnormal_value_for_bucket(record, bucket)
        rows[(record.event_id, record.ticker)] = abs(abnormal_value) if abnormal_value is not None else 0.0

    by_event: dict[str, list[tuple[str, float]]] = {}
    for (event_id, ticker), value in rows.items():
        by_event.setdefault(event_id, []).append((ticker, value))
    rank_map: dict[tuple[str, str], int] = {}
    for event_id, values in by_event.items():
        values.sort(key=lambda item: item[1], reverse=True)
        for rank, (ticker, _value) in enumerate(values, start=1):
            rank_map[(event_id, ticker)] = rank

    ranked_records: list[EventMarketReactionRecord] = []
    for record in evaluations:
        payload = record.as_flat_dict()
        payload["rank_realized_move"] = rank_map.get((record.event_id, record.ticker))
        ranked_records.append(EventMarketReactionRecord(**payload))
    return ranked_records


def _abnormal_value_for_bucket(record: EventMarketReactionRecord, bucket: str) -> float | None:
    mapping = {
        "same_day": record.abnormal_return_t0,
        "1d": record.abnormal_return_t1,
        "3d": record.abnormal_return_t3,
        "5d": record.abnormal_return_t5,
        "10d": record.abnormal_return_t10,
    }
    return mapping.get(bucket)


def _realized_lag_bucket(
    abnormal_returns: dict[str, float | None],
    predicted_direction: str,
    rules: ScoringRules,
) -> str | None:
    threshold = rules.evaluation.minimum_move_threshold
    for bucket_name, _offset in ordered_lag_buckets(rules):
        signed = _signed_value(abnormal_returns.get(bucket_name), predicted_direction)
        if signed is not None and signed >= threshold:
            return bucket_name
    best_bucket = None
    best_signed = None
    for bucket_name, _offset in ordered_lag_buckets(rules):
        signed = _signed_value(abnormal_returns.get(bucket_name), predicted_direction)
        if signed is None:
            continue
        if best_signed is None or signed > best_signed:
            best_signed = signed
            best_bucket = bucket_name
    return best_bucket if best_signed is not None and best_signed > 0 else None


def _best_signed_abnormal_return(
    abnormal_returns: dict[str, float | None],
    predicted_direction: str,
) -> float | None:
    signed_values = [
        _signed_value(value, predicted_direction)
        for value in abnormal_returns.values()
        if value is not None
    ]
    signed_values = [value for value in signed_values if value is not None]
    if not signed_values:
        return None
    return max(signed_values)


def _realized_direction(
    abnormal_returns: dict[str, float | None],
    rules: ScoringRules,
) -> str | None:
    best_value = None
    for value in abnormal_returns.values():
        if value is None:
            continue
        if best_value is None or abs(value) > abs(best_value):
            best_value = value
    if best_value is None or abs(best_value) < rules.evaluation.minimum_move_threshold:
        return "neutral"
    return "positive" if best_value > 0 else "negative"


def _hit_flag(
    abnormal_returns: dict[str, float | None],
    predicted_direction: str,
    predicted_lag_bucket: str,
    rules: ScoringRules,
) -> bool:
    hit_threshold = rules.evaluation.hit_thresholds.get(
        predicted_lag_bucket, rules.evaluation.minimum_move_threshold
    )
    for bucket_name, offset in ordered_lag_buckets(rules):
        if offset > rules.lag_buckets.get(predicted_lag_bucket, 0):
            continue
        signed = _signed_value(abnormal_returns.get(bucket_name), predicted_direction)
        if signed is not None and signed >= hit_threshold:
            return True
    return False


def _signed_value(value: float | None, predicted_direction: str) -> float | None:
    if value is None:
        return None
    if predicted_direction == "positive":
        return value
    if predicted_direction == "negative":
        return -value
    return abs(value)


def _build_price_series(frame: pd.DataFrame) -> dict[str, list[PricePoint]]:
    frame = frame.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    frame["price"] = frame["adjusted_close"].fillna(frame["close"])
    series_map: dict[str, list[PricePoint]] = {}
    for ticker, group in frame.groupby("ticker"):
        ordered = group.sort_values("trade_date")
        series_map[str(ticker)] = [
            PricePoint(
                trade_date=row["trade_date"],
                price=float(row["price"]),
                volume=float(row["volume"]) if pd.notna(row["volume"]) else None,
            )
            for row in ordered.to_dict(orient="records")
            if pd.notna(row["price"])
        ]
    return series_map


def _resolve_benchmark_ticker(
    rules: ScoringRules,
    benchmark_series: dict[str, list[PricePoint]],
) -> str | None:
    if rules.benchmark_ticker in benchmark_series:
        return rules.benchmark_ticker
    return next(iter(benchmark_series), None)


def _find_anchor_index(series: list[PricePoint], published_date: date | None) -> int | None:
    if not series:
        return None
    if published_date is None:
        return 0
    for index, point in enumerate(series):
        if point.trade_date >= published_date:
            return index
    return None


def _window_return(series: list[PricePoint], anchor_index: int | None, offset: int) -> float | None:
    if anchor_index is None:
        return None
    target_index = anchor_index + offset
    if anchor_index >= len(series) or target_index >= len(series):
        return None
    anchor_price = series[anchor_index].price
    target_price = series[target_index].price
    if anchor_price <= 0:
        return None
    return (target_price / anchor_price) - 1.0


def _abnormal_volume(
    series: list[PricePoint],
    anchor_index: int | None,
    offset: int,
    lookback_days: int,
) -> float | None:
    if anchor_index is None:
        return None
    target_index = anchor_index + offset
    if target_index >= len(series):
        return None
    current_volume = series[target_index].volume
    if current_volume is None:
        return None
    start_index = max(0, target_index - lookback_days)
    lookback = [
        point.volume for point in series[start_index:target_index] if point.volume is not None
    ]
    if not lookback:
        return None
    median_volume = float(pd.Series(lookback).median())
    if median_volume <= 0:
        return None
    return (current_volume / median_volume) - 1.0


def _peak_value(values: list[float | None]) -> float | None:
    candidates = [value for value in values if value is not None]
    if not candidates:
        return None
    return max(candidates)


def _round_optional(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


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
