from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from semicon_alpha.graph.rules import EdgeTraversalRule, load_graph_schema
from semicon_alpha.models.records import (
    EventGraphAnchorRecord,
    EventNodeInfluenceRecord,
    EventPropagationPathRecord,
    GraphEdgeRecord,
)
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, upsert_parquet


@dataclass
class PropagationState:
    current_node_id: str
    current_node_type: str
    path_nodes: list[str]
    path_edges: list[str]
    score: float
    confidence: float
    direction: str
    reason_codes: list[str]
    hop_count: int


@dataclass(frozen=True)
class TraversalEdge:
    edge_id: str
    edge_type: str
    source_node_id: str
    source_node_type: str
    target_node_id: str
    target_node_type: str
    weight: float
    sign: str
    confidence: float
    evidence: str | None
    reverse: bool = False


class GraphPropagationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.graph_nodes_path = settings.processed_dir / "graph_nodes.parquet"
        self.graph_edges_path = settings.processed_dir / "graph_edges.parquet"
        self.events_path = settings.processed_dir / "news_events_structured.parquet"
        self.event_themes_path = settings.processed_dir / "news_event_themes.parquet"
        self.anchors_path = settings.processed_dir / "event_graph_anchors.parquet"
        self.paths_path = settings.processed_dir / "event_propagation_paths.parquet"
        self.influence_path = settings.processed_dir / "event_node_influence.parquet"
        self.graph_schema_path = settings.configs_dir / "graph_schema.yaml"

    def run(self, limit: int | None = None, force: bool = False) -> dict[str, int]:
        if not self.graph_nodes_path.exists() or not self.graph_edges_path.exists():
            raise FileNotFoundError("Graph datasets are missing. Run `semicon-alpha graph-sync` first.")
        if not self.events_path.exists():
            return {"event_count": 0, "anchor_count": 0, "path_count": 0, "influence_count": 0}

        events = pd.read_parquet(self.events_path)
        if events.empty:
            return {"event_count": 0, "anchor_count": 0, "path_count": 0, "influence_count": 0}

        if not force and self.influence_path.exists():
            existing = pd.read_parquet(self.influence_path, columns=["event_id"])
            existing_event_ids = set(existing["event_id"].tolist())
            if existing_event_ids:
                events = events[~events["event_id"].isin(existing_event_ids)]

        if limit is not None:
            events = events.head(limit)
        if events.empty:
            return {"event_count": 0, "anchor_count": 0, "path_count": 0, "influence_count": 0}

        node_frame = pd.read_parquet(self.graph_nodes_path)
        edge_frame = pd.read_parquet(self.graph_edges_path)
        theme_frame = _read_optional_parquet(self.event_themes_path)
        graph_schema = load_graph_schema(self.graph_schema_path)
        processed_at = now_utc()

        node_type_map = dict(zip(node_frame["node_id"], node_frame["node_type"], strict=False))
        theme_name_to_id = {
            str(row["label"]).lower(): row["node_id"]
            for row in node_frame[node_frame["node_type"] == "theme"].to_dict(orient="records")
        }
        theme_rows_by_event = defaultdict(list)
        if not theme_frame.empty:
            for row in theme_frame.to_dict(orient="records"):
                theme_rows_by_event[row["event_id"]].append(row)

        outgoing_map, incoming_map = _build_edge_maps(edge_frame)
        anchor_records: list[EventGraphAnchorRecord] = []
        path_records: list[EventPropagationPathRecord] = []
        influence_records: list[EventNodeInfluenceRecord] = []

        for event_row in events.to_dict(orient="records"):
            event_id = event_row["event_id"]
            event_anchors = self._build_event_anchors(
                event_row=event_row,
                theme_rows=theme_rows_by_event.get(event_id, []),
                node_type_map=node_type_map,
                theme_name_to_id=theme_name_to_id,
                processed_at=processed_at,
            )
            anchor_records.extend(event_anchors)
            event_path_records, event_influence_records = self._propagate_event(
                event_id=event_id,
                anchors=event_anchors,
                node_type_map=node_type_map,
                outgoing_map=outgoing_map,
                incoming_map=incoming_map,
                graph_schema=graph_schema,
                processed_at=processed_at,
            )
            path_records.extend(event_path_records)
            influence_records.extend(event_influence_records)

        upsert_parquet(
            self.anchors_path,
            anchor_records,
            unique_keys=["event_id", "anchor_node_id", "anchor_role"],
            sort_by=["event_id", "anchor_score"],
        )
        upsert_parquet(
            self.paths_path,
            path_records,
            unique_keys=["event_id", "target_node_id", "path_rank"],
            sort_by=["event_id", "target_node_id", "path_rank"],
        )
        upsert_parquet(
            self.influence_path,
            influence_records,
            unique_keys=["event_id", "node_id"],
            sort_by=["event_id", "aggregate_influence_score"],
        )
        self.catalog.refresh_processed_views()
        return {
            "event_count": len(events),
            "anchor_count": len(anchor_records),
            "path_count": len(path_records),
            "influence_count": len(influence_records),
        }

    def _build_event_anchors(
        self,
        event_row: dict[str, object],
        theme_rows: list[dict[str, object]],
        node_type_map: dict[str, str],
        theme_name_to_id: dict[str, str],
        processed_at,
    ) -> list[EventGraphAnchorRecord]:
        event_id = str(event_row["event_id"])
        event_direction = str(event_row["direction"])
        event_confidence = float(event_row["confidence"])
        market_relevance = float(event_row["market_relevance_score"])

        anchors: list[EventGraphAnchorRecord] = []

        def add_anchor(node_id: str, role: str, score: float, reason: str) -> None:
            node_type = node_type_map.get(node_id)
            if not node_type:
                return
            anchors.append(
                EventGraphAnchorRecord(
                    event_id=event_id,
                    anchor_node_id=node_id,
                    anchor_node_type=node_type,
                    anchor_role=role,
                    anchor_score=round(max(0.01, min(0.99, score)), 4),
                    anchor_direction=event_direction,
                    anchor_confidence=round(max(0.05, min(0.99, event_confidence)), 4),
                    anchor_reason=reason,
                    processed_at_utc=processed_at,
                )
            )

        origin_companies = _parse_json_list(event_row.get("origin_companies"))
        mentioned_companies = [
            ticker for ticker in _parse_json_list(event_row.get("mentioned_companies")) if ticker not in origin_companies
        ]
        primary_themes = _parse_json_list(event_row.get("primary_themes"))
        secondary_segments = _parse_json_list(event_row.get("secondary_segments"))

        base_anchor_score = max(0.1, min(0.95, (event_confidence * 0.55) + (market_relevance * 0.45)))
        for ticker in origin_companies:
            add_anchor(
                f"company:{ticker}",
                "origin_company",
                base_anchor_score,
                f"Origin company anchor from structured event for {ticker}.",
            )
        for ticker in mentioned_companies:
            add_anchor(
                f"company:{ticker}",
                "mentioned_company",
                base_anchor_score * 0.75,
                f"Mentioned company anchor from structured event for {ticker}.",
            )

        if theme_rows:
            for row in theme_rows:
                theme_score = max(
                    0.1,
                    min(
                        0.95,
                        base_anchor_score * (0.6 if row.get("is_primary") else 0.45)
                        + float(row.get("match_score", 0.0)) * 0.2,
                    ),
                )
                add_anchor(
                    str(row["theme_id"]),
                    "primary_theme" if bool(row.get("is_primary")) else "secondary_theme",
                    theme_score,
                    f"Theme anchor derived from event theme mapping for {row['theme_name']}.",
                )
        else:
            for theme_name in primary_themes:
                theme_id = theme_name_to_id.get(str(theme_name).lower())
                if not theme_id:
                    continue
                add_anchor(
                    theme_id,
                    "primary_theme",
                    base_anchor_score * 0.65,
                    f"Theme anchor inferred from structured event primary theme '{theme_name}'.",
                )

        primary_segment = _coerce_optional_str(event_row.get("primary_segment"))
        if primary_segment:
            add_anchor(
                f"segment:{primary_segment}",
                "primary_segment",
                base_anchor_score * 0.55,
                f"Primary segment anchor inferred from structured event segment '{primary_segment}'.",
            )
        for segment in secondary_segments:
            add_anchor(
                f"segment:{segment}",
                "secondary_segment",
                base_anchor_score * 0.35,
                f"Secondary segment anchor inferred from structured event segment '{segment}'.",
            )

        deduped: dict[tuple[str, str], EventGraphAnchorRecord] = {}
        for anchor in anchors:
            key = (anchor.anchor_node_id, anchor.anchor_role)
            existing = deduped.get(key)
            if existing is None or anchor.anchor_score > existing.anchor_score:
                deduped[key] = anchor
        return sorted(
            deduped.values(),
            key=lambda record: (-record.anchor_score, record.anchor_node_id, record.anchor_role),
        )

    def _propagate_event(
        self,
        event_id: str,
        anchors: list[EventGraphAnchorRecord],
        node_type_map: dict[str, str],
        outgoing_map: dict[str, list[TraversalEdge]],
        incoming_map: dict[str, list[TraversalEdge]],
        graph_schema,
        processed_at,
    ) -> tuple[list[EventPropagationPathRecord], list[EventNodeInfluenceRecord]]:
        if not anchors:
            return [], []

        max_depth = graph_schema.propagation.max_depth
        beam_width = graph_schema.propagation.beam_width
        top_paths_per_target = graph_schema.propagation.top_paths_per_target
        min_path_score = graph_schema.propagation.min_path_score

        frontier = [
            PropagationState(
                current_node_id=anchor.anchor_node_id,
                current_node_type=anchor.anchor_node_type,
                path_nodes=[anchor.anchor_node_id],
                path_edges=[],
                score=anchor.anchor_score,
                confidence=anchor.anchor_confidence,
                direction=anchor.anchor_direction,
                reason_codes=[f"anchor_role:{anchor.anchor_role}"],
                hop_count=0,
            )
            for anchor in anchors
        ]
        paths_by_target: dict[str, list[PropagationState]] = defaultdict(list)

        for depth in range(1, max_depth + 1):
            next_states: list[PropagationState] = []
            for state in frontier:
                for candidate in self._expand_state(
                    state=state,
                    depth=depth,
                    node_type_map=node_type_map,
                    outgoing_map=outgoing_map,
                    incoming_map=incoming_map,
                    graph_schema=graph_schema,
                    min_path_score=min_path_score,
                ):
                    paths_by_target[candidate.current_node_id].append(candidate)
                    next_states.append(candidate)
            next_states.sort(key=lambda item: item.score, reverse=True)
            frontier = next_states[:beam_width]
            if not frontier:
                break

        path_records: list[EventPropagationPathRecord] = []
        influence_records: list[EventNodeInfluenceRecord] = []
        for target_node_id, states in sorted(paths_by_target.items()):
            states.sort(key=lambda item: item.score, reverse=True)
            best_states = states[:top_paths_per_target]
            node_type = node_type_map.get(target_node_id, "unknown")
            for path_rank, state in enumerate(best_states, start=1):
                path_records.append(
                    EventPropagationPathRecord(
                        event_id=event_id,
                        target_node_id=target_node_id,
                        target_node_type=node_type,
                        hop_count=state.hop_count,
                        path_rank=path_rank,
                        path_nodes=state.path_nodes,
                        path_edges=state.path_edges,
                        path_score=round(state.score, 4),
                        path_direction=state.direction,
                        path_confidence=round(state.confidence, 4),
                        reason_codes=state.reason_codes,
                        processed_at_utc=processed_at,
                    )
                )
            influence_records.append(
                self._aggregate_node_influence(
                    event_id=event_id,
                    node_id=target_node_id,
                    node_type=node_type,
                    states=states,
                    processed_at=processed_at,
                )
            )
        return path_records, influence_records

    def _expand_state(
        self,
        state: PropagationState,
        depth: int,
        node_type_map: dict[str, str],
        outgoing_map: dict[str, list[TraversalEdge]],
        incoming_map: dict[str, list[TraversalEdge]],
        graph_schema,
        min_path_score: float,
    ) -> Iterable[PropagationState]:
        transitions: list[tuple[TraversalEdge, str, str]] = []
        for edge in outgoing_map.get(state.current_node_id, []):
            transitions.append((edge, edge.target_node_id, edge.target_node_type))
        for edge in incoming_map.get(state.current_node_id, []):
            transitions.append((edge, edge.source_node_id, edge.source_node_type))

        for edge, next_node_id, next_node_type in transitions:
            if next_node_id in state.path_nodes:
                continue
            rule = _get_edge_rule(graph_schema.edge_type_rules, edge.edge_type)
            if edge.reverse and not rule.allows_reverse_traversal:
                continue

            multiplier = rule.reverse_multiplier if edge.reverse else rule.forward_multiplier
            if multiplier <= 0:
                continue
            if depth > rule.max_depth_preference:
                multiplier *= 0.5
            hop_decay = graph_schema.propagation.hop_decay.get(depth, 0.35)

            next_score = state.score * edge.weight * edge.confidence * multiplier * hop_decay
            if next_score < min_path_score:
                continue

            next_confidence = max(
                0.01,
                min(0.99, state.confidence * edge.confidence * rule.confidence_penalty),
            )
            sign_mode = rule.reverse_sign_mode if edge.reverse else rule.forward_sign_mode
            next_direction = _apply_sign_mode(state.direction, edge.sign, sign_mode)
            traversal_label = "reverse" if edge.reverse else "forward"
            yield PropagationState(
                current_node_id=next_node_id,
                current_node_type=node_type_map.get(next_node_id, next_node_type),
                path_nodes=[*state.path_nodes, next_node_id],
                path_edges=[*state.path_edges, edge.edge_id],
                score=next_score,
                confidence=next_confidence,
                direction=next_direction,
                reason_codes=[
                    *state.reason_codes,
                    f"edge_type:{edge.edge_type}",
                    f"traversal:{traversal_label}",
                ],
                hop_count=depth,
            )

    def _aggregate_node_influence(
        self,
        event_id: str,
        node_id: str,
        node_type: str,
        states: list[PropagationState],
        processed_at,
    ) -> EventNodeInfluenceRecord:
        first_order_score = sum(state.score for state in states if state.hop_count == 1)
        second_order_score = sum(state.score for state in states if state.hop_count == 2)
        third_order_score = sum(state.score for state in states if state.hop_count == 3)
        aggregate_score = min(0.99, first_order_score + second_order_score + third_order_score)
        best_state = max(states, key=lambda state: state.score)
        provisional_direction = _aggregate_direction(states)
        confidence = min(0.99, max(state.confidence for state in states))
        top_paths = [
            {
                "path_nodes": state.path_nodes,
                "path_edges": state.path_edges,
                "path_score": round(state.score, 4),
                "path_direction": state.direction,
                "hop_count": state.hop_count,
            }
            for state in sorted(states, key=lambda state: state.score, reverse=True)[:3]
        ]
        return EventNodeInfluenceRecord(
            event_id=event_id,
            node_id=node_id,
            node_type=node_type,
            best_hop_count=best_state.hop_count,
            path_count=len(states),
            direct_path_score=round(max((state.score for state in states if state.hop_count == 1), default=0.0), 4),
            first_order_score=round(first_order_score, 4),
            second_order_score=round(second_order_score, 4),
            third_order_score=round(third_order_score, 4),
            aggregate_influence_score=round(aggregate_score, 4),
            provisional_direction=provisional_direction,
            confidence=round(confidence, 4),
            top_paths=top_paths,
            processed_at_utc=processed_at,
        )


def _build_edge_maps(
    edge_frame: pd.DataFrame,
) -> tuple[dict[str, list[TraversalEdge]], dict[str, list[TraversalEdge]]]:
    outgoing_map: dict[str, list[TraversalEdge]] = defaultdict(list)
    incoming_map: dict[str, list[TraversalEdge]] = defaultdict(list)
    for row in edge_frame.to_dict(orient="records"):
        edge = TraversalEdge(
            edge_id=row["edge_id"],
            edge_type=row["edge_type"],
            source_node_id=row["source_node_id"],
            source_node_type=row["source_node_type"],
            target_node_id=row["target_node_id"],
            target_node_type=row["target_node_type"],
            weight=float(row["weight"]),
            sign=row["sign"],
            confidence=float(row["confidence"]),
            evidence=row.get("evidence"),
            reverse=False,
        )
        outgoing_map[edge.source_node_id].append(edge)
        incoming_map[edge.target_node_id].append(
            TraversalEdge(**{**edge.__dict__, "reverse": True})
        )
    return outgoing_map, incoming_map


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
        value = value.strip()
        if not value:
            return []
        if value.startswith("["):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def _coerce_optional_str(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _get_edge_rule(edge_type_rules: dict[str, EdgeTraversalRule], edge_type: str) -> EdgeTraversalRule:
    return edge_type_rules.get(
        edge_type,
        EdgeTraversalRule(
            forward_multiplier=0.4,
            reverse_multiplier=0.4,
            allows_reverse_traversal=True,
            confidence_penalty=0.9,
            max_depth_preference=3,
        ),
    )


def _apply_sign_mode(current_direction: str, edge_sign: str, sign_mode: str) -> str:
    if current_direction in {"ambiguous", "mixed"}:
        return current_direction
    if sign_mode == "preserve":
        return current_direction
    if sign_mode == "invert":
        return "negative" if current_direction == "positive" else "positive"
    if sign_mode == "mixed":
        return "mixed"

    if edge_sign == "negative":
        return "negative" if current_direction == "positive" else "positive"
    if edge_sign == "mixed":
        return "mixed"
    return current_direction


def _aggregate_direction(states: list[PropagationState]) -> str:
    weighted_score = 0.0
    saw_mixed = False
    for state in states:
        if state.direction == "positive":
            weighted_score += state.score
        elif state.direction == "negative":
            weighted_score -= state.score
        elif state.direction == "mixed":
            saw_mixed = True
    if abs(weighted_score) < 0.02:
        return "mixed" if saw_mixed else "ambiguous"
    return "positive" if weighted_score > 0 else "negative"
