from __future__ import annotations

from typing import Any

from semicon_alpha.services.helpers import clean_record, has_columns, parse_json_list, parse_json_value
from semicon_alpha.services.repository import WorldModelRepository


class EvidenceService:
    def __init__(self, repo: WorldModelRepository) -> None:
        self.repo = repo

    def get_event_evidence(self, event_id: str) -> dict[str, Any]:
        event_row = self._get_event_row(event_id)
        article_id = event_row.get("article_id")
        article_record = self._get_article_record(article_id)
        classifications = self._event_classifications(event_id)
        themes = self._event_themes(event_id)
        observations = [
            f"Headline: {event_row.get('headline')}",
            f"Event type: {event_row.get('event_type')}",
            f"Direction / severity: {event_row.get('direction')} / {event_row.get('severity')}",
        ]
        if article_record.get("supporting_snippet"):
            observations.append(article_record["supporting_snippet"])

        return {
            "event_id": event_id,
            "article_id": article_id,
            "observations": observations,
            "source_documents": [article_record or self._event_document_fallback(event_row)],
            "classifications": classifications[:6],
            "theme_mappings": themes[:8],
        }

    def get_relation_evidence(self, relation_id: str) -> dict[str, Any] | None:
        frames = [
            self.repo.company_relationships,
            self.repo.theme_relationships,
            self.repo.ontology_relationships,
            self.repo.graph_edges,
        ]
        for frame in frames:
            if frame.empty or "edge_id" not in frame.columns:
                continue
            match = frame.loc[frame["edge_id"] == relation_id]
            if match.empty:
                continue
            row = clean_record(match.iloc[0].to_dict())
            return {
                "relation_id": relation_id,
                "evidence": row.get("evidence"),
                "evidence_url": row.get("evidence_url"),
                "confidence": row.get("confidence"),
                "weight": row.get("weight"),
                "edge_type": row.get("edge_type"),
                "source_id": row.get("source_id") or row.get("source_node_id"),
                "target_id": row.get("target_id") or row.get("target_node_id"),
                "effective_start": row.get("effective_start"),
                "effective_end": row.get("effective_end"),
                "relationship_status": row.get("relationship_status"),
            }
        return None

    def get_path_evidence(self, edge_ids: list[str]) -> list[dict[str, Any]]:
        evidence_rows = []
        for edge_id in edge_ids:
            row = self.get_relation_evidence(edge_id)
            if row is not None:
                evidence_rows.append(row)
        return evidence_rows

    def get_entity_evidence(self, entity_id: str, limit: int = 6) -> dict[str, Any]:
        linked_events = self._linked_entity_events(entity_id, limit=limit)
        graph_edges = self.repo.graph_edges
        match = graph_edges.loc[
            (graph_edges["source_node_id"] == entity_id) | (graph_edges["target_node_id"] == entity_id)
        ].sort_values(["confidence", "weight"], ascending=[False, False])

        relation_rows = []
        for row in match.head(limit).to_dict(orient="records"):
            relation_rows.append(
                {
                    "edge_id": row["edge_id"],
                    "edge_type": row["edge_type"],
                    "other_node_id": row["target_node_id"] if row["source_node_id"] == entity_id else row["source_node_id"],
                    "evidence": row.get("evidence"),
                    "confidence": row.get("confidence"),
                    "weight": row.get("weight"),
                    "effective_start": row.get("effective_start"),
                    "effective_end": row.get("effective_end"),
                    "relationship_status": row.get("relationship_status"),
                }
            )
        return {"linked_events": linked_events, "relationship_evidence": relation_rows}

    def _linked_entity_events(self, entity_id: str, limit: int) -> list[dict[str, Any]]:
        ticker = entity_id.split(":", 1)[1] if ":" in entity_id else entity_id
        linked_events = []
        scores = self.repo.event_scores
        if has_columns(scores, "entity_id"):
            linked_scores = scores.loc[scores["entity_id"] == entity_id].sort_values("published_at_utc", ascending=False)
            for row in linked_scores.head(limit).to_dict(orient="records"):
                linked_events.append(
                    {
                        "event_id": row["event_id"],
                        "headline": self._event_row_value(row["event_id"], "headline"),
                        "explanation": row.get("explanation"),
                        "top_paths": parse_json_value(row.get("top_paths"), []),
                    }
                )
        elif ticker:
            linked_scores = scores.loc[scores["ticker"] == ticker].sort_values("published_at_utc", ascending=False)
            for row in linked_scores.head(limit).to_dict(orient="records"):
                linked_events.append(
                    {
                        "event_id": row["event_id"],
                        "headline": self._event_row_value(row["event_id"], "headline"),
                        "explanation": row.get("explanation"),
                        "top_paths": parse_json_value(row.get("top_paths"), []),
                    }
                )

        if not linked_events and has_columns(self.repo.event_influences, "node_id"):
            influences = self.repo.event_influences.loc[
                self.repo.event_influences["node_id"] == entity_id
            ].sort_values("aggregate_influence_score", ascending=False)
            for row in influences.head(limit).to_dict(orient="records"):
                linked_events.append(
                    {
                        "event_id": row["event_id"],
                        "headline": self._event_row_value(row["event_id"], "headline"),
                        "explanation": f"Retained as a graph-influence node with score {row.get('aggregate_influence_score')}.",
                        "top_paths": parse_json_value(row.get("top_paths"), []),
                    }
                )
        return linked_events

    def _get_event_row(self, event_id: str) -> dict[str, Any]:
        match = self.repo.events.loc[self.repo.events["event_id"] == event_id]
        if match.empty:
            raise KeyError(f"Unknown event_id: {event_id}")
        return clean_record(match.iloc[0].to_dict())

    def _get_article_record(self, article_id: str | None) -> dict[str, Any]:
        if not article_id:
            return {}
        enriched = self.repo.articles_enriched
        discovered = self.repo.articles_discovered
        record: dict[str, Any] = {}
        if has_columns(enriched, "article_id"):
            match = enriched.loc[enriched["article_id"] == article_id]
            if not match.empty:
                row = clean_record(match.iloc[0].to_dict())
                record.update(
                    {
                        "article_id": article_id,
                        "title": row.get("title"),
                        "source_url": row.get("source_url"),
                        "canonical_url": row.get("canonical_url"),
                        "site_name": row.get("site_name"),
                        "published_at_utc": row.get("published_at_utc"),
                        "supporting_snippet": _build_supporting_snippet(row),
                    }
                )
        if not record and has_columns(discovered, "article_id"):
            match = discovered.loc[discovered["article_id"] == article_id]
            if not match.empty:
                row = clean_record(match.iloc[0].to_dict())
                record.update(
                    {
                        "article_id": article_id,
                        "title": row.get("title"),
                        "source_url": row.get("source_url"),
                        "site_name": row.get("source_slug"),
                        "published_at_utc": None,
                        "supporting_snippet": row.get("summary_snippet"),
                    }
                )
        return record

    def _event_row_value(self, event_id: str, key: str) -> Any:
        match = self.repo.events.loc[self.repo.events["event_id"] == event_id]
        if match.empty:
            return None
        value = match.iloc[0].to_dict().get(key)
        return None if value is None else value

    def _event_classifications(self, event_id: str) -> list[dict[str, Any]]:
        frame = self.repo.event_classifications
        if not has_columns(frame, "event_id"):
            return []
        ordered = frame.loc[frame["event_id"] == event_id]
        if "is_selected" in ordered.columns and "score" in ordered.columns:
            ordered = ordered.sort_values(["is_selected", "score"], ascending=[False, False])
        return [clean_record(row) for row in ordered.to_dict(orient="records")]

    def _event_themes(self, event_id: str) -> list[dict[str, Any]]:
        frame = self.repo.event_themes
        if not has_columns(frame, "event_id"):
            return []
        ordered = frame.loc[frame["event_id"] == event_id]
        if "is_primary" in ordered.columns and "match_score" in ordered.columns:
            ordered = ordered.sort_values(["is_primary", "match_score"], ascending=[False, False])
        return [clean_record(row) for row in ordered.to_dict(orient="records")]

    def _event_document_fallback(self, event_row: dict[str, Any]) -> dict[str, Any]:
        snippet = event_row.get("summary") or event_row.get("reasoning")
        return {
            "article_id": event_row.get("article_id"),
            "title": event_row.get("headline"),
            "source_url": event_row.get("source_url"),
            "canonical_url": event_row.get("canonical_url"),
            "site_name": event_row.get("source"),
            "published_at_utc": event_row.get("published_at_utc"),
            "supporting_snippet": snippet,
        }


def _build_supporting_snippet(row: dict[str, Any]) -> str | None:
    for field in ("excerpt", "description", "body_text"):
        value = row.get(field)
        if not value:
            continue
        text = str(value).strip().replace("\n", " ")
        if not text:
            continue
        return text[:320]
    return None
