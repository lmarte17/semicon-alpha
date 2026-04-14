from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from semicon_alpha.appstate import AppStateRepository
from semicon_alpha.graph.rules import EdgeTraversalRule, load_graph_schema
from semicon_alpha.services.helpers import clean_record, entity_id_to_ticker, has_columns, parse_json_value
from semicon_alpha.services.operational_support import matched_event_rows, resolve_item_label
from semicon_alpha.services.repository import WorldModelRepository
from semicon_alpha.settings import Settings


@dataclass
class ScenarioPropagationState:
    current_node_id: str
    current_node_type: str
    path_nodes: list[str]
    path_edges: list[dict[str, Any]]
    score: float
    confidence: float
    direction: str
    assumption_id: str
    hop_count: int


@dataclass(frozen=True)
class ScenarioTraversalEdge:
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


class ScenarioService:
    def __init__(
        self,
        settings: Settings,
        repo: WorldModelRepository,
        appstate: AppStateRepository,
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.appstate = appstate
        self.graph_schema = load_graph_schema(settings.configs_dir / "graph_schema.yaml")
        self.node_map = {
            str(row["node_id"]): clean_record(row)
            for row in self.repo.graph_nodes.to_dict(orient="records")
        }
        self.outgoing_map: dict[str, list[ScenarioTraversalEdge]] = defaultdict(list)
        self.incoming_map: dict[str, list[ScenarioTraversalEdge]] = defaultdict(list)
        for row in self.repo.graph_edges.to_dict(orient="records"):
            edge = ScenarioTraversalEdge(
                edge_id=str(row["edge_id"]),
                edge_type=str(row["edge_type"]),
                source_node_id=str(row["source_node_id"]),
                source_node_type=str(row["source_node_type"]),
                target_node_id=str(row["target_node_id"]),
                target_node_type=str(row["target_node_type"]),
                weight=float(row["weight"]),
                sign=str(row["sign"]),
                confidence=float(row["confidence"]),
                evidence=row.get("evidence"),
                reverse=False,
            )
            self.outgoing_map[edge.source_node_id].append(edge)
            self.incoming_map[edge.target_node_id].append(
                ScenarioTraversalEdge(**{**edge.__dict__, "reverse": True})
            )

    def list_scenarios(self) -> list[dict[str, Any]]:
        return self.appstate.list_scenarios()

    def create_scenario(
        self,
        name: str,
        description: str | None = None,
        summary: str | None = None,
        assumptions: list[dict[str, Any]] | None = None,
        monitors: list[dict[str, Any]] | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        scenario = self.appstate.create_scenario(
            name=name,
            description=description,
            summary=summary,
            status=status,
        )
        scenario_id = str(scenario["scenario_id"])
        created_assumptions: list[dict[str, Any]] = []
        for assumption in assumptions or []:
            created_assumptions.append(
                self.appstate.add_scenario_assumption(
                    scenario_id=scenario_id,
                    item_type=str(assumption["item_type"]),
                    item_id_value=str(assumption["item_id"]),
                    expected_direction=str(assumption["direction"]),
                    label=assumption.get("label") or self._resolve_label(str(assumption["item_type"]), str(assumption["item_id"])),
                    magnitude=str(assumption.get("magnitude") or "medium"),
                    confidence=float(assumption.get("confidence") or 0.7),
                    rationale=assumption.get("rationale"),
                )
            )

        monitor_items = monitors or [
            {
                "item_type": assumption["item_type"],
                "item_id": assumption["item_id"],
                "expected_direction": assumption["direction"],
                "label": assumption.get("label"),
                "threshold": {"origin": "default_assumption_monitor"},
            }
            for assumption in assumptions or []
        ]
        for monitor in monitor_items:
            self.appstate.add_scenario_monitor(
                scenario_id=scenario_id,
                item_type=str(monitor["item_type"]),
                item_id_value=str(monitor["item_id"]),
                expected_direction=_coerce_optional_str(monitor.get("expected_direction")),
                label=monitor.get("label") or self._resolve_label(str(monitor["item_type"]), str(monitor["item_id"])),
                threshold=monitor.get("threshold"),
            )

        if created_assumptions:
            self.run_scenario(scenario_id)
        return self.get_scenario_workspace(scenario_id)

    def get_scenario_workspace(
        self,
        scenario_id: str,
        alerts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        scenario = self.appstate.get_scenario(scenario_id)
        if scenario is None:
            raise KeyError(f"Unknown scenario_id: {scenario_id}")
        assumptions = self.appstate.list_scenario_assumptions(scenario_id)
        monitors = self.appstate.list_scenario_monitors(scenario_id)
        run_history = self.appstate.list_scenario_runs(scenario_id, limit=8)
        latest_run = run_history[0] if run_history else None
        signals = self.get_monitor_signals(scenario_id, limit=16)
        related_alerts = [
            alert
            for alert in (alerts or [])
            if scenario_id in (alert.get("scenario_ids_json") or [])
        ]
        return {
            "scenario": scenario,
            "assumptions": assumptions,
            "monitors": monitors,
            "latest_run": latest_run,
            "run_history": run_history,
            "support_signals": [signal for signal in signals if signal["signal_state"] == "support"],
            "contradiction_signals": [signal for signal in signals if signal["signal_state"] == "contradiction"],
            "alerts": related_alerts[:16],
        }

    def run_scenario(self, scenario_id: str) -> dict[str, Any]:
        scenario = self.appstate.get_scenario(scenario_id)
        if scenario is None:
            raise KeyError(f"Unknown scenario_id: {scenario_id}")
        assumptions = self.appstate.list_scenario_assumptions(scenario_id)
        if not assumptions:
            raise KeyError(f"Scenario {scenario_id} has no assumptions.")

        impacted_entities: dict[str, dict[str, Any]] = {}
        path_candidates: list[dict[str, Any]] = []

        for assumption in assumptions:
            assumption_item_type = str(assumption["item_type"])
            if assumption_item_type in {"event_type", "event"}:
                rows, paths = self._run_historical_assumption(assumption)
            else:
                rows, paths = self._run_graph_assumption(assumption)
            for row in rows:
                entity_id = str(row["entity_id"])
                existing = impacted_entities.get(entity_id)
                if existing is None:
                    impacted_entities[entity_id] = row
                    continue
                existing["positive_score"] += row.get("positive_score", 0.0)
                existing["negative_score"] += row.get("negative_score", 0.0)
                existing["total_score"] += row.get("total_score", 0.0)
                existing["confidence"] = max(existing["confidence"], row.get("confidence", 0.0))
                existing["supporting_assumptions"] = sorted(
                    {
                        *existing["supporting_assumptions"],
                        *row.get("supporting_assumptions", []),
                    }
                )
                existing["top_paths"] = sorted(
                    [*existing["top_paths"], *row.get("top_paths", [])],
                    key=lambda item: item.get("score", 0.0),
                    reverse=True,
                )[:4]
                existing["direction"] = _aggregate_direction_from_scores(
                    existing["positive_score"],
                    existing["negative_score"],
                )
                existing["best_hop_count"] = min(existing["best_hop_count"], row.get("best_hop_count", 3))
            path_candidates.extend(paths)

        ordered_entities = sorted(
            (
                {
                    **row,
                    "positive_score": round(row["positive_score"], 4),
                    "negative_score": round(row["negative_score"], 4),
                    "total_score": round(row["total_score"], 4),
                    "confidence": round(row["confidence"], 4),
                }
                for row in impacted_entities.values()
            ),
            key=lambda row: (row["total_score"], row["confidence"]),
            reverse=True,
        )[:18]
        ordered_paths = sorted(path_candidates, key=lambda row: row["score"], reverse=True)[:20]
        signals = self.get_monitor_signals(scenario_id, limit=16)
        run_summary = self._build_run_summary(scenario, assumptions, ordered_entities)
        run = self.appstate.create_scenario_run(
            scenario_id=scenario_id,
            run_summary=run_summary,
            assumptions=assumptions,
            impacted_entities=ordered_entities,
            affected_paths=ordered_paths,
            support_signals=[signal for signal in signals if signal["signal_state"] == "support"],
            contradiction_signals=[signal for signal in signals if signal["signal_state"] == "contradiction"],
        )
        return run

    def get_monitor_signals(self, scenario_id: str, limit: int = 12) -> list[dict[str, Any]]:
        scenario = self.appstate.get_scenario(scenario_id)
        if scenario is None:
            raise KeyError(f"Unknown scenario_id: {scenario_id}")
        subjects = self.appstate.list_scenario_monitors(scenario_id) or self.appstate.list_scenario_assumptions(scenario_id)
        signals: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for subject in subjects:
            item_type = str(subject["item_type"])
            item_id = str(subject["item_id_value"])
            expected_direction = _coerce_optional_str(subject.get("expected_direction"))
            for signal in self.collect_item_signals(
                item_type=item_type,
                item_id=item_id,
                expected_direction=expected_direction,
                limit=max(4, limit),
            ):
                fingerprint = (
                    signal["item_type"],
                    signal["item_id"],
                    signal.get("event_id") or signal.get("headline") or "",
                )
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                signals.append({**signal, "scenario_id": scenario_id})
        signals.sort(key=lambda row: (row.get("published_at_utc") or "", row.get("score_hint") or 0.0), reverse=True)
        return signals[:limit]

    def collect_item_signals(
        self,
        item_type: str,
        item_id: str,
        expected_direction: str | None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        if item_type == "entity":
            return self._entity_signals(item_id, expected_direction, limit=limit)
        if item_type in {"theme", "segment", "event_type"}:
            return self._event_row_signals(item_type, item_id, expected_direction, limit=limit)
        if item_type == "event":
            event_row = self.repo.events.loc[self.repo.events["event_id"] == item_id]
            if event_row.empty:
                return []
            row = clean_record(event_row.iloc[0].to_dict())
            state = _signal_state(row.get("direction"), expected_direction)
            if state == "neutral":
                return []
            return [
                {
                    "signal_state": state,
                    "item_type": item_type,
                    "item_id": item_id,
                    "item_label": row.get("headline") or item_id,
                    "event_id": item_id,
                    "headline": row.get("headline"),
                    "direction": row.get("direction"),
                    "severity": row.get("severity"),
                    "published_at_utc": row.get("published_at_utc"),
                    "score_hint": float(row.get("market_relevance_score") or 0.0),
                    "reason": "Linked event direction matched the monitored scenario direction."
                    if state == "support"
                    else "Linked event direction weakened the monitored scenario direction.",
                }
            ]
        return []

    def _run_graph_assumption(self, assumption: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        node_id = self._scenario_item_to_node_id(str(assumption["item_type"]), str(assumption["item_id_value"]))
        if not node_id or node_id not in self.node_map:
            return [], []

        start_score = _magnitude_score(str(assumption.get("magnitude") or "medium")) * float(
            assumption.get("confidence") or 0.7
        )
        start_direction = str(assumption["expected_direction"])
        assumption_id = str(assumption["assumption_id"])
        frontier = [
            ScenarioPropagationState(
                current_node_id=node_id,
                current_node_type=str(self.node_map[node_id]["node_type"]),
                path_nodes=[node_id],
                path_edges=[],
                score=start_score,
                confidence=float(assumption.get("confidence") or 0.7),
                direction=start_direction,
                assumption_id=assumption_id,
                hop_count=0,
            )
        ]
        states_by_entity: dict[str, list[ScenarioPropagationState]] = defaultdict(list)
        path_rows: list[dict[str, Any]] = []

        if self.node_map[node_id]["node_type"] == "company":
            states_by_entity[node_id].append(frontier[0])

        for depth in range(1, self.graph_schema.propagation.max_depth + 1):
            next_frontier: list[ScenarioPropagationState] = []
            for state in frontier:
                for candidate in self._expand_state(state, depth):
                    next_frontier.append(candidate)
                    if candidate.current_node_type == "company":
                        states_by_entity[candidate.current_node_id].append(candidate)
                        path_rows.append(
                            {
                                "assumption_id": assumption_id,
                                "entity_id": candidate.current_node_id,
                                "label": self._node_label(candidate.current_node_id),
                                "direction": candidate.direction,
                                "score": round(candidate.score, 4),
                                "hop_count": candidate.hop_count,
                                "path_nodes": candidate.path_nodes,
                                "path_edges": candidate.path_edges,
                            }
                        )
            next_frontier.sort(key=lambda item: item.score, reverse=True)
            frontier = next_frontier[: self.graph_schema.propagation.beam_width]
            if not frontier:
                break

        impacted_entities: list[dict[str, Any]] = []
        for entity_id, states in states_by_entity.items():
            positive_score = sum(state.score for state in states if state.direction == "positive")
            negative_score = sum(state.score for state in states if state.direction == "negative")
            total_score = positive_score + negative_score if positive_score or negative_score else sum(
                state.score for state in states
            )
            ticker = entity_id_to_ticker(entity_id)
            impacted_entities.append(
                {
                    "entity_id": entity_id,
                    "ticker": ticker,
                    "label": self._node_label(entity_id),
                    "direction": _aggregate_direction_from_scores(positive_score, negative_score),
                    "positive_score": positive_score,
                    "negative_score": negative_score,
                    "total_score": total_score,
                    "confidence": max(state.confidence for state in states),
                    "best_hop_count": min(state.hop_count for state in states),
                    "supporting_assumptions": [assumption_id],
                    "top_paths": [
                        {
                            "score": round(state.score, 4),
                            "direction": state.direction,
                            "hop_count": state.hop_count,
                            "path_nodes": state.path_nodes,
                            "path_edges": state.path_edges,
                        }
                        for state in sorted(states, key=lambda state: state.score, reverse=True)[:3]
                    ],
                }
            )
        return impacted_entities, path_rows

    def _run_historical_assumption(
        self,
        assumption: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        assumption_id = str(assumption["assumption_id"])
        base_score = _magnitude_score(str(assumption.get("magnitude") or "medium")) * float(
            assumption.get("confidence") or 0.7
        )
        item_type = str(assumption["item_type"])
        item_id = str(assumption["item_id_value"])

        if item_type == "event":
            event_ids = [item_id]
        else:
            frame = self.repo.events
            frame = frame.loc[frame["event_type"] == item_id].sort_values("published_at_utc", ascending=False)
            event_ids = [str(row["event_id"]) for row in frame.head(6).to_dict(orient="records")]

        impacted: dict[str, dict[str, Any]] = {}
        paths: list[dict[str, Any]] = []
        if not event_ids or not has_columns(self.repo.event_scores, "event_id", "entity_id", "ticker"):
            return [], []

        for index, event_id in enumerate(event_ids):
            decay = max(0.35, 1.0 - (index * 0.12))
            event_row = self.repo.events.loc[self.repo.events["event_id"] == event_id]
            if event_row.empty:
                continue
            event_direction = _coerce_optional_str(event_row.iloc[0].to_dict().get("direction")) or "positive"
            flip = event_direction != str(assumption["expected_direction"])
            match = self.repo.event_scores.loc[self.repo.event_scores["event_id"] == event_id].sort_values(
                "total_rank_score",
                ascending=False,
            )
            for row in match.head(8).to_dict(orient="records"):
                entity_id = str(row["entity_id"])
                path_score = float(row.get("total_rank_score") or 0.0) * base_score * decay
                direction = _invert_direction(str(row.get("impact_direction") or "mixed")) if flip else str(
                    row.get("impact_direction") or "mixed"
                )
                record = impacted.setdefault(
                    entity_id,
                    {
                        "entity_id": entity_id,
                        "ticker": str(row["ticker"]),
                        "label": self._node_label(entity_id),
                        "positive_score": 0.0,
                        "negative_score": 0.0,
                        "total_score": 0.0,
                        "confidence": float(row.get("confidence") or 0.0),
                        "best_hop_count": 1,
                        "supporting_assumptions": [assumption_id],
                        "top_paths": [],
                    },
                )
                if direction == "positive":
                    record["positive_score"] += path_score
                elif direction == "negative":
                    record["negative_score"] += path_score
                record["total_score"] += path_score
                record["confidence"] = max(record["confidence"], float(row.get("confidence") or 0.0))
                top_paths = parse_json_value(row.get("top_paths"), [])
                normalized_paths = [
                    {
                        "score": round(path_score * float(path.get("path_score") or 1.0), 4),
                        "direction": direction,
                        "hop_count": path.get("hop_count") or 1,
                        "path_nodes": path.get("path_nodes") or [entity_id],
                        "path_edges": path.get("path_edges") or [],
                    }
                    for path in top_paths[:2]
                ]
                record["top_paths"] = sorted(
                    [*record["top_paths"], *normalized_paths],
                    key=lambda item: item.get("score", 0.0),
                    reverse=True,
                )[:4]
                paths.extend(
                    {
                        "assumption_id": assumption_id,
                        "entity_id": entity_id,
                        "label": self._node_label(entity_id),
                        "direction": direction,
                        "score": path["score"],
                        "hop_count": path.get("hop_count") or 1,
                        "path_nodes": path.get("path_nodes") or [entity_id],
                        "path_edges": path.get("path_edges") or [],
                    }
                    for path in normalized_paths
                )

        impacted_entities = []
        for row in impacted.values():
            impacted_entities.append(
                {
                    **row,
                    "direction": _aggregate_direction_from_scores(row["positive_score"], row["negative_score"]),
                }
            )
        impacted_entities.sort(key=lambda row: row["total_score"], reverse=True)
        return impacted_entities, paths

    def _expand_state(self, state: ScenarioPropagationState, depth: int) -> Iterable[ScenarioPropagationState]:
        transitions: list[tuple[ScenarioTraversalEdge, str, str]] = []
        for edge in self.outgoing_map.get(state.current_node_id, []):
            transitions.append((edge, edge.target_node_id, edge.target_node_type))
        for edge in self.incoming_map.get(state.current_node_id, []):
            transitions.append((edge, edge.source_node_id, edge.source_node_type))

        for edge, next_node_id, next_node_type in transitions:
            if next_node_id in state.path_nodes:
                continue
            rule = _edge_rule(self.graph_schema.edge_type_rules, edge.edge_type)
            if edge.reverse and not rule.allows_reverse_traversal:
                continue
            multiplier = rule.reverse_multiplier if edge.reverse else rule.forward_multiplier
            if multiplier <= 0:
                continue
            if depth > rule.max_depth_preference:
                multiplier *= 0.5
            hop_decay = self.graph_schema.propagation.hop_decay.get(depth, 0.35)
            next_score = state.score * edge.weight * edge.confidence * multiplier * hop_decay
            if next_score < self.graph_schema.propagation.min_path_score:
                continue
            next_confidence = max(0.01, min(0.99, state.confidence * edge.confidence * rule.confidence_penalty))
            sign_mode = rule.reverse_sign_mode if edge.reverse else rule.forward_sign_mode
            next_direction = _apply_sign_mode(state.direction, edge.sign, sign_mode)
            yield ScenarioPropagationState(
                current_node_id=next_node_id,
                current_node_type=next_node_type,
                path_nodes=[*state.path_nodes, next_node_id],
                path_edges=[
                    *state.path_edges,
                    {
                        "edge_id": edge.edge_id,
                        "edge_type": edge.edge_type,
                        "source_node_id": edge.source_node_id,
                        "target_node_id": edge.target_node_id,
                        "traversal": "reverse" if edge.reverse else "forward",
                        "weight": round(edge.weight, 4),
                        "confidence": round(edge.confidence, 4),
                        "evidence": edge.evidence,
                    },
                ],
                score=next_score,
                confidence=next_confidence,
                direction=next_direction,
                assumption_id=state.assumption_id,
                hop_count=depth,
            )

    def _resolve_label(self, item_type: str, item_id: str) -> str:
        if item_type in {"entity", "theme", "segment", "event_type"}:
            return resolve_item_label(self.repo, item_type, item_id)
        if item_type == "event":
            match = self.repo.events.loc[self.repo.events["event_id"] == item_id]
            if not match.empty:
                return str(match.iloc[0]["headline"])
        return item_id

    def _scenario_item_to_node_id(self, item_type: str, item_id: str) -> str | None:
        if item_type == "entity":
            return item_id
        if item_type == "theme":
            return item_id
        if item_type == "segment":
            return f"segment:{item_id}" if not item_id.startswith("segment:") else item_id
        return None

    def _node_label(self, node_id: str) -> str:
        node = self.node_map.get(node_id)
        if not node:
            return node_id
        return str(node.get("label") or node_id)

    def _entity_signals(
        self,
        entity_id: str,
        expected_direction: str | None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        scores = self.repo.event_scores
        if not has_columns(scores, "event_id", "entity_id", "impact_direction"):
            return []
        ticker = entity_id_to_ticker(entity_id)
        match = scores.loc[scores["entity_id"] == entity_id]
        if ticker and "ticker" in scores.columns:
            match = scores.loc[(scores["entity_id"] == entity_id) | (scores["ticker"] == ticker)]
        if "published_at_utc" in match.columns:
            match = match.sort_values("published_at_utc", ascending=False)
        signals = []
        for row in match.head(limit).to_dict(orient="records"):
            signal_state = _signal_state(row.get("impact_direction"), expected_direction)
            if signal_state == "neutral":
                continue
            headline = self._event_headline(str(row["event_id"]))
            signals.append(
                {
                    "signal_state": signal_state,
                    "item_type": "entity",
                    "item_id": entity_id,
                    "item_label": self._node_label(entity_id),
                    "event_id": str(row["event_id"]),
                    "headline": headline,
                    "direction": row.get("impact_direction"),
                    "severity": None,
                    "published_at_utc": row.get("published_at_utc"),
                    "score_hint": float(row.get("total_rank_score") or 0.0),
                    "reason": "Recent scored impact aligned with the monitored scenario."
                    if signal_state == "support"
                    else "Recent scored impact moved against the monitored scenario.",
                }
            )
        return signals

    def _event_row_signals(
        self,
        item_type: str,
        item_id: str,
        expected_direction: str | None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        signals = []
        for row in matched_event_rows(self.repo, item_type, item_id, limit=limit):
            signal_state = _signal_state(row.get("direction"), expected_direction)
            if signal_state == "neutral":
                continue
            signals.append(
                {
                    "signal_state": signal_state,
                    "item_type": item_type,
                    "item_id": item_id,
                    "item_label": self._resolve_label(item_type, item_id),
                    "event_id": str(row["event_id"]),
                    "headline": row.get("headline"),
                    "direction": row.get("direction"),
                    "severity": row.get("severity"),
                    "published_at_utc": row.get("published_at_utc"),
                    "score_hint": float(row.get("market_relevance_score") or 0.0),
                    "reason": "Observed event flow aligned with the monitored scenario."
                    if signal_state == "support"
                    else "Observed event flow weakened the monitored scenario.",
                }
            )
        return signals

    def _event_headline(self, event_id: str) -> str | None:
        match = self.repo.events.loc[self.repo.events["event_id"] == event_id]
        if match.empty:
            return None
        value = match.iloc[0].to_dict().get("headline")
        return None if value is None else str(value)

    def _build_run_summary(
        self,
        scenario: dict[str, Any],
        assumptions: list[dict[str, Any]],
        impacted_entities: list[dict[str, Any]],
    ) -> str:
        if not impacted_entities:
            return f"{scenario['name']} did not produce any ranked impacted entities from the current graph context."
        leaders = ", ".join(
            f"{row['ticker']} ({row['direction']}, {row['total_score']:.2f})"
            for row in impacted_entities[:3]
            if row.get("ticker")
        )
        return (
            f"{scenario['name']} ran {len(assumptions)} explicit assumptions and currently points most strongly toward "
            f"{leaders or 'no clear leaders'}."
        )


def _magnitude_score(value: str) -> float:
    return {
        "low": 0.32,
        "medium": 0.58,
        "high": 0.84,
    }.get(value.lower(), 0.58)


def _signal_state(observed_direction: Any, expected_direction: str | None) -> str:
    observed = _coerce_optional_str(observed_direction)
    expected = _coerce_optional_str(expected_direction)
    if not observed or not expected or observed in {"mixed", "ambiguous"}:
        return "neutral"
    if observed == expected:
        return "support"
    return "contradiction"


def _aggregate_direction_from_scores(positive_score: float, negative_score: float) -> str:
    if abs(positive_score - negative_score) < 0.02:
        return "mixed"
    return "positive" if positive_score >= negative_score else "negative"


def _invert_direction(direction: str) -> str:
    if direction == "positive":
        return "negative"
    if direction == "negative":
        return "positive"
    return direction


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _edge_rule(edge_type_rules: dict[str, EdgeTraversalRule], edge_type: str) -> EdgeTraversalRule:
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
        return _invert_direction(current_direction)
    if sign_mode == "mixed":
        return "mixed"
    if edge_sign == "negative":
        return _invert_direction(current_direction)
    if edge_sign == "mixed":
        return "mixed"
    return current_direction
