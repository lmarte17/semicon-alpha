from __future__ import annotations

from collections import defaultdict
from typing import Any

from semicon_alpha.services.helpers import clean_record, parse_json_list
from semicon_alpha.services.repository import WorldModelRepository


class DashboardService:
    def __init__(self, repo: WorldModelRepository) -> None:
        self.repo = repo

    def get_overview(self, limit: int = 12) -> dict[str, Any]:
        events = self.repo.events
        scores = self.repo.event_scores
        event_themes = self.repo.event_themes
        evaluations = self.repo.event_reactions
        summary = self.repo.evaluation_summary

        themes_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in event_themes.to_dict(orient="records"):
            themes_by_event[str(row["event_id"])].append(clean_record(row))

        scores_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if not scores.empty:
            ordered_scores = scores.sort_values("total_rank_score", ascending=False)
            for row in ordered_scores.to_dict(orient="records"):
                scores_by_event[str(row["event_id"])].append(clean_record(row))

        recent_events: list[dict[str, Any]] = []
        for row in events.head(limit).to_dict(orient="records"):
            event_id = str(row["event_id"])
            top_impacts = scores_by_event.get(event_id, [])[:5]
            recent_events.append(
                {
                    "event_id": event_id,
                    "headline": row["headline"],
                    "published_at_utc": row.get("published_at_utc"),
                    "event_type": row["event_type"],
                    "direction": row["direction"],
                    "severity": row["severity"],
                    "confidence": row["confidence"],
                    "source": row["source"],
                    "primary_themes": parse_json_list(row.get("primary_themes")),
                    "top_themes": [
                        {
                            "theme_id": theme["theme_id"],
                            "theme_name": theme["theme_name"],
                            "is_primary": bool(theme.get("is_primary")),
                        }
                        for theme in themes_by_event.get(event_id, [])[:4]
                    ],
                    "top_impacts": [
                        {
                            "ticker": impact["ticker"],
                            "impact_direction": impact["impact_direction"],
                            "total_rank_score": impact["total_rank_score"],
                            "predicted_lag_bucket": impact["predicted_lag_bucket"],
                            "is_non_obvious": bool(impact.get("is_non_obvious")),
                        }
                        for impact in top_impacts
                    ],
                }
            )

        top_non_obvious_impacts = []
        if not scores.empty:
            for row in (
                scores[scores["is_non_obvious"].fillna(False)]
                .sort_values("total_rank_score", ascending=False)
                .head(12)
                .to_dict(orient="records")
            ):
                top_non_obvious_impacts.append(
                    {
                        "event_id": row["event_id"],
                        "ticker": row["ticker"],
                        "headline": _event_headline(events, row["event_id"]),
                        "total_rank_score": row["total_rank_score"],
                        "predicted_lag_bucket": row["predicted_lag_bucket"],
                        "impact_direction": row["impact_direction"],
                        "confidence": row["confidence"],
                    }
                )

        evaluation_metrics = {
            row["metric_name"]: row["metric_value"] for row in summary.to_dict(orient="records")
        }
        metrics = {
            "event_count": int(len(events)),
            "tracked_entities": int(len(self.repo.company_registry)),
            "impact_candidate_count": int(len(scores)),
            "evaluated_prediction_count": int(len(evaluations)),
            "delayed_impact_hit_rate": evaluation_metrics.get("delayed_impact_hit_rate"),
        }
        return {
            "metrics": metrics,
            "recent_events": recent_events,
            "top_non_obvious_impacts": top_non_obvious_impacts,
        }


def _event_headline(events, event_id: str) -> str | None:
    match = events.loc[events["event_id"] == event_id]
    if match.empty:
        return None
    return str(match.iloc[0]["headline"])
