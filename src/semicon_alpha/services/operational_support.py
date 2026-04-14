from __future__ import annotations

from typing import Any

from semicon_alpha.services.helpers import clean_record, entity_id_to_ticker, has_columns, parse_json_value
from semicon_alpha.services.repository import WorldModelRepository


def resolve_item_label(repo: WorldModelRepository, item_type: str, item_id: str) -> str:
    if item_type == "entity":
        nodes = repo.graph_nodes
        if has_columns(nodes, "node_id", "label"):
            match = nodes.loc[nodes["node_id"] == item_id]
            if not match.empty:
                return str(match.iloc[0]["label"])
        return item_id
    if item_type == "theme":
        if has_columns(repo.theme_nodes, "node_id", "theme_name"):
            match = repo.theme_nodes.loc[repo.theme_nodes["node_id"] == item_id]
            if not match.empty:
                return str(match.iloc[0]["theme_name"])
        return item_id
    if item_type in {"event_type", "segment"}:
        return item_id.replace("_", " ")
    return item_id


def matched_event_rows(
    repo: WorldModelRepository,
    item_type: str,
    item_id: str,
    limit: int = 25,
) -> list[dict[str, Any]]:
    events = repo.events
    if events.empty:
        return []

    event_ids: list[str] = []
    if item_type == "entity" and has_columns(repo.event_scores, "event_id"):
        ticker = entity_id_to_ticker(item_id)
        scores = repo.event_scores
        mask = scores["entity_id"].eq(item_id)
        if ticker and "ticker" in scores.columns:
            mask = mask | scores["ticker"].eq(ticker)
        event_ids = [str(value) for value in scores.loc[mask, "event_id"].dropna().tolist()]
    elif item_type == "theme" and has_columns(repo.event_themes, "event_id", "theme_id"):
        event_ids = [
            str(value)
            for value in repo.event_themes.loc[repo.event_themes["theme_id"] == item_id, "event_id"]
            .dropna()
            .tolist()
        ]
    elif item_type == "event_type":
        event_ids = [str(value) for value in events.loc[events["event_type"] == item_id, "event_id"].tolist()]
    elif item_type == "segment":
        ids = []
        for row in events.to_dict(orient="records"):
            primary_segment = row.get("primary_segment")
            secondary_segments = parse_json_value(row.get("secondary_segments"), [])
            if primary_segment == item_id or item_id in secondary_segments:
                ids.append(str(row["event_id"]))
        event_ids = ids

    if not event_ids:
        return []

    unique_event_ids = list(dict.fromkeys(event_ids))
    matched = events.loc[events["event_id"].isin(unique_event_ids)].sort_values(
        "published_at_utc", ascending=False
    )
    return [clean_record(row) for row in matched.head(limit).to_dict(orient="records")]


def event_summary_card(
    repo: WorldModelRepository,
    event_row: dict[str, Any],
    limit_impacts: int = 3,
) -> dict[str, Any]:
    event_id = str(event_row["event_id"])
    impacts = top_event_impacts(repo, event_id, limit=limit_impacts)
    return {
        "event_id": event_id,
        "headline": event_row.get("headline"),
        "published_at_utc": event_row.get("published_at_utc"),
        "event_type": event_row.get("event_type"),
        "direction": event_row.get("direction"),
        "severity": event_row.get("severity"),
        "source": event_row.get("source"),
        "top_impacts": impacts,
    }


def top_event_impacts(repo: WorldModelRepository, event_id: str, limit: int = 5) -> list[dict[str, Any]]:
    scores = repo.event_scores
    if not has_columns(scores, "event_id"):
        return []
    match = scores.loc[scores["event_id"] == event_id].sort_values("total_rank_score", ascending=False)
    rows = []
    for row in match.head(limit).to_dict(orient="records"):
        rows.append(
            {
                "entity_id": row.get("entity_id"),
                "ticker": row.get("ticker"),
                "impact_direction": row.get("impact_direction"),
                "total_rank_score": row.get("total_rank_score"),
                "predicted_lag_bucket": row.get("predicted_lag_bucket"),
                "confidence": row.get("confidence"),
            }
        )
    return rows


def related_alerts_for_items(
    alerts: list[dict[str, Any]],
    item_ids: list[str],
) -> list[dict[str, Any]]:
    item_set = set(item_ids)
    related: list[dict[str, Any]] = []
    for alert in alerts:
        entities = set(alert.get("entity_ids_json") or [])
        themes = set(alert.get("theme_ids_json") or [])
        events = set(alert.get("event_ids_json") or [])
        scenarios = set(alert.get("scenario_ids_json") or [])
        theses = set(alert.get("thesis_ids_json") or [])
        if item_set & entities or item_set & themes or item_set & events or item_set & scenarios or item_set & theses:
            related.append(alert)
    return related
