from __future__ import annotations

from typing import Any

from semicon_alpha.services.evidence import EvidenceService
from semicon_alpha.services.graph_view import GraphExplorerService
from semicon_alpha.services.helpers import clean_record, entity_id_to_ticker, has_columns, parse_json_value
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
        ticker = entity_id_to_ticker(entity_id) if node["node_type"] == "company" else None
        registry_row = self._get_company_row(ticker) if ticker else None
        neighbors = self.graph_service.get_neighbors(entity_id, max_items=20)
        recent_events = self.get_entity_events(entity_id, limit=10)
        effect_pathways = self._effect_pathways(entity_id, limit=10)
        exposure_summary = self._exposure_summary(entity_id, recent_events)
        evidence = self.evidence_service.get_entity_evidence(entity_id)
        history = self.get_entity_history(entity_id, limit=20)
        metadata = parse_json_value(node.get("metadata_json"), {})
        entity = {
            "entity_id": entity_id,
            "node_type": node["node_type"],
            "label": node["label"],
            "description": node.get("description"),
            "ticker": registry_row.get("ticker") if registry_row else node.get("ticker"),
            "company_name": registry_row.get("company_name") if registry_row else node.get("label"),
            "segment_primary": registry_row.get("segment_primary") if registry_row else node.get("segment_primary"),
            "segment_secondary": parse_json_value(registry_row.get("segment_secondary"), []) if registry_row else [],
            "ecosystem_role": registry_row.get("ecosystem_role") if registry_row else metadata.get("ecosystem_role"),
            "market_cap_bucket": registry_row.get("market_cap_bucket") if registry_row else metadata.get("market_cap_bucket"),
            "country": registry_row.get("country") if registry_row else metadata.get("country"),
            "notes": registry_row.get("notes") if registry_row else None,
            "metadata": metadata,
        }
        return {
            "entity": entity,
            "neighbors": neighbors,
            "recent_events": recent_events,
            "exposure_summary": exposure_summary,
            "effect_pathways": effect_pathways,
            "evidence": evidence,
            "history": history,
        }

    def list_entities(
        self,
        *,
        node_type: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        frame = self.repo.graph_nodes.copy()
        if frame.empty:
            return []
        if node_type:
            frame = frame.loc[frame["node_type"] == node_type]
        if query:
            lowered = query.lower().strip()
            if lowered:
                mask = (
                    frame["label"].fillna("").str.lower().str.contains(lowered)
                    | frame["description"].fillna("").str.lower().str.contains(lowered)
                    | frame["node_type"].fillna("").str.lower().str.contains(lowered)
                )
                frame = frame.loc[mask]
        frame = frame.sort_values(["node_type", "label"], ascending=[True, True]).head(limit)
        return [clean_record(row) for row in frame.to_dict(orient="records")]

    def get_entity_events(self, entity_id: str, limit: int = 10) -> list[dict[str, Any]]:
        node = self._get_node(entity_id)
        if node["node_type"] == "company":
            return self._company_events(entity_id, limit)
        return self._graph_node_events(entity_id, limit)

    def get_entity_history(self, entity_id: str, limit: int = 20) -> list[dict[str, Any]]:
        frame = self.repo.graph_change_log
        if frame.empty:
            return []
        mask = (
            frame["node_id"].fillna("") == entity_id
        ) | (
            frame["source_node_id"].fillna("") == entity_id
        ) | (
            frame["target_node_id"].fillna("") == entity_id
        )
        ordered = frame.loc[mask].sort_values("snapshot_at_utc", ascending=False)
        rows = []
        for row in ordered.head(limit).to_dict(orient="records"):
            payload = clean_record(row)
            rows.append(
                {
                    "snapshot_at_utc": payload.get("snapshot_at_utc"),
                    "object_type": payload.get("object_type"),
                    "change_type": payload.get("change_type"),
                    "summary": payload.get("summary"),
                    "edge_type": payload.get("edge_type"),
                    "source_node_id": payload.get("source_node_id"),
                    "target_node_id": payload.get("target_node_id"),
                }
            )
        return rows

    def _company_events(self, entity_id: str, limit: int) -> list[dict[str, Any]]:
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
                    "node_score": row["total_rank_score"],
                }
            )
        return events

    def _graph_node_events(self, entity_id: str, limit: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen_event_ids: set[str] = set()
        if has_columns(self.repo.event_influences, "node_id"):
            influences = self.repo.event_influences.loc[
                self.repo.event_influences["node_id"] == entity_id
            ].sort_values("aggregate_influence_score", ascending=False)
            for row in influences.to_dict(orient="records"):
                if row["event_id"] in seen_event_ids:
                    continue
                seen_event_ids.add(row["event_id"])
                event_row = self.repo.events.loc[self.repo.events["event_id"] == row["event_id"]]
                if event_row.empty:
                    continue
                event = clean_record(event_row.iloc[0].to_dict())
                results.append(
                    {
                        "event_id": event["event_id"],
                        "headline": event.get("headline"),
                        "published_at_utc": event.get("published_at_utc"),
                        "impact_direction": row.get("provisional_direction"),
                        "total_rank_score": row.get("aggregate_influence_score"),
                        "predicted_lag_bucket": None,
                        "confidence": row.get("confidence"),
                        "is_non_obvious": None,
                        "node_score": row.get("aggregate_influence_score"),
                    }
                )
                if len(results) >= limit:
                    return results

        if entity_id.startswith("theme:") and has_columns(self.repo.event_themes, "theme_id"):
            theme_rows = self.repo.event_themes.loc[
                self.repo.event_themes["theme_id"] == entity_id
            ].sort_values("match_score", ascending=False)
            for row in theme_rows.to_dict(orient="records"):
                if row["event_id"] in seen_event_ids:
                    continue
                seen_event_ids.add(row["event_id"])
                event_row = self.repo.events.loc[self.repo.events["event_id"] == row["event_id"]]
                if event_row.empty:
                    continue
                event = clean_record(event_row.iloc[0].to_dict())
                results.append(
                    {
                        "event_id": event["event_id"],
                        "headline": event.get("headline"),
                        "published_at_utc": event.get("published_at_utc"),
                        "impact_direction": event.get("direction"),
                        "total_rank_score": row.get("match_score"),
                        "predicted_lag_bucket": None,
                        "confidence": event.get("confidence"),
                        "is_non_obvious": None,
                        "node_score": row.get("match_score"),
                    }
                )
                if len(results) >= limit:
                    break

        results.sort(key=lambda item: ((item.get("published_at_utc") or ""), float(item.get("node_score") or 0.0)), reverse=True)
        return results[:limit]

    def _effect_pathways(self, entity_id: str, limit: int = 10) -> list[dict[str, Any]]:
        node = self._get_node(entity_id)
        if node["node_type"] == "company" and not self.repo.event_scores.empty:
            match = self.repo.event_scores.loc[self.repo.event_scores["entity_id"] == entity_id].sort_values(
                "total_rank_score", ascending=False
            )
            return [
                {
                    "event_id": row["event_id"],
                    "impact_direction": row["impact_direction"],
                    "total_rank_score": row["total_rank_score"],
                    "predicted_lag_bucket": row["predicted_lag_bucket"],
                    "explanation": row.get("explanation"),
                    "top_paths": parse_json_value(row.get("top_paths"), []),
                }
                for row in match.head(limit).to_dict(orient="records")
            ]

        if not has_columns(self.repo.event_influences, "node_id"):
            return []
        match = self.repo.event_influences.loc[
            self.repo.event_influences["node_id"] == entity_id
        ].sort_values("aggregate_influence_score", ascending=False)
        pathways = []
        for row in match.head(limit).to_dict(orient="records"):
            pathways.append(
                {
                    "event_id": row["event_id"],
                    "impact_direction": row.get("provisional_direction"),
                    "total_rank_score": row.get("aggregate_influence_score"),
                    "predicted_lag_bucket": None,
                    "explanation": f"{node['label']} is retained through graph influence paths for {row['event_id']}.",
                    "top_paths": parse_json_value(row.get("top_paths"), []),
                }
            )
        return pathways

    def _exposure_summary(self, entity_id: str, recent_events: list[dict[str, Any]]) -> dict[str, Any]:
        node = self._get_node(entity_id)
        if node["node_type"] == "company" and not self.repo.event_scores.empty:
            match = self.repo.event_scores.loc[self.repo.event_scores["entity_id"] == entity_id]
            return _summary_from_company_scores(match, recent_events)
        if not has_columns(self.repo.event_influences, "node_id"):
            return _empty_summary()
        match = self.repo.event_influences.loc[self.repo.event_influences["node_id"] == entity_id]
        if match.empty:
            return _empty_summary()
        top_row = match.sort_values("aggregate_influence_score", ascending=False).iloc[0]
        return {
            "event_count": int(len(match)),
            "avg_rank_score": round(float(match["aggregate_influence_score"].mean()), 4),
            "avg_confidence": round(float(match["confidence"].mean()), 4),
            "top_event": {
                "event_id": top_row["event_id"],
                "headline": recent_events[0]["headline"] if recent_events else None,
                "total_rank_score": top_row["aggregate_influence_score"],
                "predicted_lag_bucket": None,
            },
            "positive_exposure_count": int((match["provisional_direction"] == "positive").sum()),
            "negative_exposure_count": int((match["provisional_direction"] == "negative").sum()),
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


def _summary_from_company_scores(match, recent_events: list[dict[str, Any]]) -> dict[str, Any]:
    if match.empty:
        return _empty_summary()
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


def _empty_summary() -> dict[str, Any]:
    return {
        "event_count": 0,
        "avg_rank_score": None,
        "avg_confidence": None,
        "top_event": None,
        "positive_exposure_count": 0,
        "negative_exposure_count": 0,
    }
