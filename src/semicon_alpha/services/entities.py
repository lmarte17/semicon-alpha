from __future__ import annotations

from typing import Any

from semicon_alpha.services.evidence import EvidenceService
from semicon_alpha.services.graph_view import GraphExplorerService
from semicon_alpha.services.helpers import clean_record, entity_id_to_ticker, parse_json_value
from semicon_alpha.services.repository import WorldModelRepository


class EntityWorkspaceService:
    def __init__(
        self,
        repo: WorldModelRepository,
        graph_service: GraphExplorerService,
        evidence_service: EvidenceService,
    ) -> None:
        self.repo = repo
        self.graph_service = graph_service
        self.evidence_service = evidence_service

    def get_entity_workspace(self, entity_id: str) -> dict[str, Any]:
        node = self._get_node(entity_id)
        ticker = entity_id_to_ticker(entity_id)
        registry_row = self._get_company_row(ticker) if node["node_type"] == "company" else None
        neighbors = self.graph_service.get_neighbors(entity_id, max_items=20)
        recent_events = self.get_entity_events(entity_id, limit=10)
        effect_pathways = self._effect_pathways(ticker, limit=10)
        exposure_summary = self._exposure_summary(ticker, recent_events)
        evidence = self.evidence_service.get_entity_evidence(entity_id)
        entity = {
            "entity_id": entity_id,
            "node_type": node["node_type"],
            "label": node["label"],
            "description": node.get("description"),
            "ticker": registry_row.get("ticker") if registry_row else node.get("ticker"),
            "company_name": registry_row.get("company_name") if registry_row else node.get("label"),
            "segment_primary": registry_row.get("segment_primary") if registry_row else node.get("segment_primary"),
            "segment_secondary": parse_json_value(registry_row.get("segment_secondary"), []) if registry_row else [],
            "ecosystem_role": registry_row.get("ecosystem_role") if registry_row else None,
            "market_cap_bucket": registry_row.get("market_cap_bucket") if registry_row else None,
            "country": registry_row.get("country") if registry_row else None,
            "notes": registry_row.get("notes") if registry_row else None,
            "metadata": parse_json_value(node.get("metadata_json"), {}),
        }
        return {
            "entity": entity,
            "neighbors": neighbors,
            "recent_events": recent_events,
            "exposure_summary": exposure_summary,
            "effect_pathways": effect_pathways,
            "evidence": evidence,
        }

    def get_entity_events(self, entity_id: str, limit: int = 10) -> list[dict[str, Any]]:
        ticker = entity_id_to_ticker(entity_id)
        if not ticker or self.repo.event_scores.empty:
            return []
        scores = self.repo.event_scores
        match = scores.loc[scores["ticker"] == ticker].sort_values("published_at_utc", ascending=False)
        events = []
        for row in match.head(limit).to_dict(orient="records"):
            event_row = self.repo.events.loc[self.repo.events["event_id"] == row["event_id"]]
            headline = None if event_row.empty else event_row.iloc[0]["headline"]
            events.append(
                {
                    "event_id": row["event_id"],
                    "headline": headline,
                    "published_at_utc": row.get("published_at_utc"),
                    "impact_direction": row["impact_direction"],
                    "total_rank_score": row["total_rank_score"],
                    "predicted_lag_bucket": row["predicted_lag_bucket"],
                    "confidence": row["confidence"],
                    "is_non_obvious": bool(row.get("is_non_obvious")),
                }
            )
        return events

    def _effect_pathways(self, ticker: str | None, limit: int = 10) -> list[dict[str, Any]]:
        if not ticker or self.repo.event_scores.empty:
            return []
        match = self.repo.event_scores.loc[self.repo.event_scores["ticker"] == ticker].sort_values(
            "total_rank_score", ascending=False
        )
        pathways = []
        for row in match.head(limit).to_dict(orient="records"):
            pathways.append(
                {
                    "event_id": row["event_id"],
                    "impact_direction": row["impact_direction"],
                    "total_rank_score": row["total_rank_score"],
                    "predicted_lag_bucket": row["predicted_lag_bucket"],
                    "explanation": row.get("explanation"),
                    "top_paths": parse_json_value(row.get("top_paths"), []),
                }
            )
        return pathways

    def _exposure_summary(self, ticker: str | None, recent_events: list[dict[str, Any]]) -> dict[str, Any]:
        if not ticker or self.repo.event_scores.empty:
            return {
                "event_count": 0,
                "avg_rank_score": None,
                "avg_confidence": None,
                "top_event": None,
                "positive_exposure_count": 0,
                "negative_exposure_count": 0,
            }
        match = self.repo.event_scores.loc[self.repo.event_scores["ticker"] == ticker]
        if match.empty:
            return {
                "event_count": 0,
                "avg_rank_score": None,
                "avg_confidence": None,
                "top_event": None,
                "positive_exposure_count": 0,
                "negative_exposure_count": 0,
            }
        top_row = match.sort_values("total_rank_score", ascending=False).iloc[0]
        return {
            "event_count": int(len(match)),
            "avg_rank_score": round(float(match["total_rank_score"].mean()), 4),
            "avg_confidence": round(float(match["confidence"].mean()), 4),
            "top_event": {
                "event_id": top_row["event_id"],
                "headline": recent_events[0]["headline"] if recent_events else None,
                "total_rank_score": top_row["total_rank_score"],
                "predicted_lag_bucket": top_row["predicted_lag_bucket"],
            },
            "positive_exposure_count": int((match["impact_direction"] == "positive").sum()),
            "negative_exposure_count": int((match["impact_direction"] == "negative").sum()),
        }

    def _get_node(self, entity_id: str) -> dict[str, Any]:
        match = self.repo.graph_nodes.loc[self.repo.graph_nodes["node_id"] == entity_id]
        if match.empty:
            raise KeyError(f"Unknown entity_id: {entity_id}")
        return clean_record(match.iloc[0].to_dict())

    def _get_company_row(self, ticker: str | None) -> dict[str, Any] | None:
        if not ticker:
            return None
        match = self.repo.company_registry.loc[self.repo.company_registry["ticker"] == ticker]
        if match.empty:
            return None
        return clean_record(match.iloc[0].to_dict())
