from __future__ import annotations

from typing import Any

from semicon_alpha.services.evidence import EvidenceService
from semicon_alpha.services.helpers import clean_record, has_columns, parse_json_value
from semicon_alpha.services.repository import WorldModelRepository


class EventWorkspaceService:
    def __init__(self, repo: WorldModelRepository, evidence_service: EvidenceService) -> None:
        self.repo = repo
        self.evidence_service = evidence_service

    def list_events(self, limit: int = 50, query: str | None = None) -> list[dict[str, Any]]:
        frame = self.repo.events
        if query:
            lowered = query.lower().strip()
            if lowered:
                mask = (
                    frame["headline"].fillna("").str.lower().str.contains(lowered)
                    | frame["event_type"].fillna("").str.lower().str.contains(lowered)
                    | frame["summary"].fillna("").str.lower().str.contains(lowered)
                )
                frame = frame[mask]
        rows = []
        for row in frame.head(limit).to_dict(orient="records"):
            rows.append(self._format_event_summary(clean_record(row)))
        return rows

    def get_event_workspace(self, event_id: str) -> dict[str, Any]:
        event_row = self._get_event_row(event_id)
        impacts = self.get_event_impacts(event_id, limit=12)
        paths = self._event_paths(event_id)
        evidence = self.evidence_service.get_event_evidence(event_id)
        themes = self._event_themes(event_id)
        historical_analogs = self._historical_analogs(event_row)
        competing_interpretations = self._competing_interpretations(impacts)
        return {
            "event": self._format_event_summary(event_row),
            "impact_candidates": impacts,
            "propagation_paths": paths,
            "themes": themes[:8],
            "supporting_evidence": evidence,
            "competing_interpretations": competing_interpretations,
            "historical_analogs": historical_analogs,
        }

    def get_event_impacts(self, event_id: str, limit: int = 20) -> list[dict[str, Any]]:
        scores = self.repo.event_scores
        if scores.empty:
            return []
        match = scores.loc[scores["event_id"] == event_id].sort_values("total_rank_score", ascending=False)
        impacts: list[dict[str, Any]] = []
        for row in match.head(limit).to_dict(orient="records"):
            impacts.append(
                {
                    "ticker": row["ticker"],
                    "entity_id": row["entity_id"],
                    "impact_direction": row["impact_direction"],
                    "direct_exposure_score": row["direct_exposure_score"],
                    "second_order_score": row["second_order_score"],
                    "third_order_score": row["third_order_score"],
                    "total_rank_score": row["total_rank_score"],
                    "predicted_lag_bucket": row["predicted_lag_bucket"],
                    "confidence": row["confidence"],
                    "is_non_obvious": bool(row.get("is_non_obvious")),
                    "explanation": row.get("explanation"),
                    "top_paths": parse_json_value(row.get("top_paths"), []),
                }
            )
        return impacts

    def _format_event_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        event_id = str(row["event_id"])
        top_impacts = self.get_event_impacts(event_id, limit=5)
        return {
            "event_id": event_id,
            "headline": row.get("headline"),
            "published_at_utc": row.get("published_at_utc"),
            "event_type": row.get("event_type"),
            "direction": row.get("direction"),
            "severity": row.get("severity"),
            "confidence": row.get("confidence"),
            "market_relevance_score": row.get("market_relevance_score"),
            "source": row.get("source"),
            "source_url": row.get("source_url"),
            "summary": row.get("summary"),
            "reasoning": row.get("reasoning"),
            "origin_companies": parse_json_value(row.get("origin_companies"), []),
            "mentioned_companies": parse_json_value(row.get("mentioned_companies"), []),
            "primary_themes": parse_json_value(row.get("primary_themes"), []),
            "primary_segment": row.get("primary_segment"),
            "secondary_segments": parse_json_value(row.get("secondary_segments"), []),
            "top_impacts": top_impacts,
        }

    def _event_paths(self, event_id: str, limit: int = 16) -> list[dict[str, Any]]:
        paths = self.repo.event_paths
        if not has_columns(paths, "event_id"):
            return []
        match = paths.loc[paths["event_id"] == event_id].sort_values("path_score", ascending=False)
        records = []
        for row in match.head(limit).to_dict(orient="records"):
            records.append(
                {
                    "target_node_id": row["target_node_id"],
                    "target_node_type": row["target_node_type"],
                    "hop_count": row["hop_count"],
                    "path_rank": row["path_rank"],
                    "path_score": row["path_score"],
                    "path_direction": row["path_direction"],
                    "path_nodes": parse_json_value(row.get("path_nodes"), []),
                    "path_edges": parse_json_value(row.get("path_edges"), []),
                    "reason_codes": parse_json_value(row.get("reason_codes"), []),
                }
            )
        return records

    def _historical_analogs(self, event_row: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        events = self.repo.events
        event_type = event_row.get("event_type")
        event_id = event_row.get("event_id")
        if event_type is None:
            return []
        match = events.loc[
            (events["event_type"] == event_type) & (events["event_id"] != event_id)
        ].sort_values("published_at_utc", ascending=False)
        analogs = []
        for row in match.head(limit).to_dict(orient="records"):
            analogs.append(
                {
                    "event_id": row["event_id"],
                    "headline": row["headline"],
                    "published_at_utc": row.get("published_at_utc"),
                    "direction": row.get("direction"),
                    "severity": row.get("severity"),
                }
            )
        return analogs

    def _competing_interpretations(self, impacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not impacts:
            return []
        positive = [impact for impact in impacts if impact["impact_direction"] == "positive"][:3]
        negative = [impact for impact in impacts if impact["impact_direction"] == "negative"][:3]
        interpretations = []
        if positive:
            interpretations.append(
                {
                    "label": "Positive transmission",
                    "summary": "Top ranked paths suggest positive spillover into beneficiaries and adjacent suppliers.",
                    "tickers": [row["ticker"] for row in positive],
                }
            )
        if negative:
            interpretations.append(
                {
                    "label": "Negative transmission",
                    "summary": "Some paths imply downside or competitive displacement for exposed names.",
                    "tickers": [row["ticker"] for row in negative],
                }
            )
        if not interpretations:
            interpretations.append(
                {
                    "label": "Mixed interpretation",
                    "summary": "Current impact set is directional but limited; users should inspect path evidence directly.",
                    "tickers": [impact["ticker"] for impact in impacts[:3]],
                }
            )
        return interpretations

    def _event_themes(self, event_id: str) -> list[dict[str, Any]]:
        themes = self.repo.event_themes
        if not has_columns(themes, "event_id"):
            return []
        ordered = themes.loc[themes["event_id"] == event_id]
        if "is_primary" in ordered.columns and "match_score" in ordered.columns:
            ordered = ordered.sort_values(["is_primary", "match_score"], ascending=[False, False])
        return [clean_record(row) for row in ordered.to_dict(orient="records")]

    def _get_event_row(self, event_id: str) -> dict[str, Any]:
        match = self.repo.events.loc[self.repo.events["event_id"] == event_id]
        if match.empty:
            raise KeyError(f"Unknown event_id: {event_id}")
        return clean_record(match.iloc[0].to_dict())
