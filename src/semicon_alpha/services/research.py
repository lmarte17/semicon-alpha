from __future__ import annotations

from collections import Counter
from typing import Any

from semicon_alpha.retrieval.index import cosine_similarity, parse_embedding
from semicon_alpha.services.events import EventWorkspaceService
from semicon_alpha.services.helpers import has_columns, parse_json_value
from semicon_alpha.services.operational_support import top_event_impacts
from semicon_alpha.services.repository import WorldModelRepository


class ResearchService:
    def __init__(self, repo: WorldModelRepository, event_service: EventWorkspaceService) -> None:
        self.repo = repo
        self.event_service = event_service

    def get_event_analogs(self, event_id: str, limit: int = 8) -> list[dict[str, Any]]:
        current = self._event_row(event_id)
        current_theme_ids = set(self._theme_ids(event_id))
        current_impacts = {impact["ticker"] for impact in top_event_impacts(self.repo, event_id, limit=5)}
        current_embedding = self._event_embedding(event_id)
        analogs: list[dict[str, Any]] = []
        for row in self.repo.events.to_dict(orient="records"):
            other_id = str(row["event_id"])
            if other_id == event_id:
                continue
            score = 0.0
            reasons: list[str] = []
            if row.get("event_type") == current.get("event_type"):
                score += 2.0
                reasons.append("same event type")
            if row.get("direction") == current.get("direction"):
                score += 1.0
                reasons.append("same direction")
            if row.get("severity") == current.get("severity"):
                score += 0.5
                reasons.append("same severity")
            if row.get("primary_segment") == current.get("primary_segment"):
                score += 1.0
                reasons.append("same primary segment")

            other_theme_ids = set(self._theme_ids(other_id))
            shared_themes = sorted(current_theme_ids & other_theme_ids)
            if shared_themes:
                score += min(2.0, 0.75 * len(shared_themes))
                reasons.append(f"shared themes: {', '.join(shared_themes[:2])}")

            other_impacts = {impact["ticker"] for impact in top_event_impacts(self.repo, other_id, limit=5)}
            shared_impacts = sorted(current_impacts & other_impacts)
            if shared_impacts:
                score += min(1.5, 0.5 * len(shared_impacts))
                reasons.append(f"shared impacted companies: {', '.join(shared_impacts[:3])}")

            other_embedding = self._event_embedding(other_id)
            semantic_score = cosine_similarity(current_embedding, other_embedding)
            if semantic_score > 0:
                score += min(2.5, semantic_score * 2.5)
                reasons.append(f"semantic match: {round(semantic_score, 2)}")

            if score <= 0:
                continue
            analogs.append(
                {
                    "event_id": other_id,
                    "headline": row.get("headline"),
                    "published_at_utc": row.get("published_at_utc"),
                    "similarity_score": round(score, 2),
                    "similarity_reasons": reasons,
                    "shared_themes": shared_themes,
                    "shared_impacts": shared_impacts,
                    "realized_summary": self._event_reaction_summary(other_id),
                }
            )
        analogs.sort(key=lambda row: (row["similarity_score"], row.get("published_at_utc") or ""), reverse=True)
        return analogs[:limit]

    def get_event_backtest(self, event_id: str) -> dict[str, Any]:
        event_workspace = self.event_service.get_event_workspace(event_id)
        scores = self.repo.event_scores
        reactions = self.repo.event_reactions
        merged_rows: list[dict[str, Any]] = []
        if has_columns(scores, "event_id", "ticker"):
            score_match = scores.loc[scores["event_id"] == event_id].sort_values("total_rank_score", ascending=False)
            for row in score_match.to_dict(orient="records"):
                ticker = str(row["ticker"])
                reaction_match = (
                    reactions.loc[(reactions["event_id"] == event_id) & (reactions["ticker"] == ticker)]
                    if has_columns(reactions, "event_id", "ticker")
                    else reactions.iloc[0:0]
                )
                reaction = {} if reaction_match.empty else reaction_match.iloc[0].to_dict()
                merged_rows.append(
                    {
                        "ticker": ticker,
                        "predicted_direction": row.get("impact_direction"),
                        "predicted_lag_bucket": row.get("predicted_lag_bucket"),
                        "predicted_rank_score": row.get("total_rank_score"),
                        "predicted_confidence": row.get("confidence"),
                        "realized_lag_bucket": reaction.get("realized_lag_bucket"),
                        "best_signed_abnormal_return": reaction.get("best_signed_abnormal_return"),
                        "hit_flag": reaction.get("hit_flag"),
                        "realized_move_rank": reaction.get("realized_move_rank"),
                        "explanation": row.get("explanation"),
                    }
                )

        hit_count = sum(1 for row in merged_rows if row.get("hit_flag"))
        lag_counter = Counter(row.get("realized_lag_bucket") or "unknown" for row in merged_rows if row.get("realized_lag_bucket"))
        best_row = max(
            merged_rows,
            key=lambda row: abs(float(row.get("best_signed_abnormal_return") or 0.0)),
            default=None,
        )
        return {
            "event": event_workspace["event"],
            "predicted_vs_realized": merged_rows,
            "summary": {
                "candidate_count": len(merged_rows),
                "hit_count": hit_count,
                "miss_count": max(0, len(merged_rows) - hit_count),
                "realized_lag_distribution": dict(lag_counter),
                "best_realized_candidate": best_row,
            },
            "supporting_evidence": event_workspace["supporting_evidence"],
        }

    def _event_row(self, event_id: str) -> dict[str, Any]:
        match = self.repo.events.loc[self.repo.events["event_id"] == event_id]
        if match.empty:
            raise KeyError(f"Unknown event_id: {event_id}")
        return match.iloc[0].to_dict()

    def _theme_ids(self, event_id: str) -> list[str]:
        if has_columns(self.repo.event_themes, "event_id", "theme_id"):
            match = self.repo.event_themes.loc[self.repo.event_themes["event_id"] == event_id]
            if not match.empty:
                return [str(value) for value in match["theme_id"].dropna().tolist()]
        event_row = self._event_row(event_id)
        return [str(value) for value in parse_json_value(event_row.get("primary_themes"), [])]

    def _event_reaction_summary(self, event_id: str) -> dict[str, Any]:
        if not has_columns(self.repo.event_reactions, "event_id"):
            return {}
        match = self.repo.event_reactions.loc[self.repo.event_reactions["event_id"] == event_id]
        if match.empty:
            return {}
        hit_rate = float(match["hit_flag"].fillna(False).mean()) if "hit_flag" in match.columns else None
        best_row = match.loc[match["best_signed_abnormal_return"].abs().idxmax()] if "best_signed_abnormal_return" in match.columns else None
        return {
            "reaction_count": int(len(match)),
            "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
            "best_ticker": None if best_row is None else best_row.get("ticker"),
            "best_signed_abnormal_return": None
            if best_row is None
            else best_row.get("best_signed_abnormal_return"),
        }

    def _event_embedding(self, event_id: str) -> list[float]:
        if not has_columns(self.repo.retrieval_index, "item_id", "search_category", "embedding_vector"):
            return []
        match = self.repo.retrieval_index.loc[
            (self.repo.retrieval_index["item_id"] == event_id)
            & (self.repo.retrieval_index["search_category"] == "events")
        ]
        if match.empty:
            return []
        return parse_embedding(match.iloc[0].get("embedding_vector"))
