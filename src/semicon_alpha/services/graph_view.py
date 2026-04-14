from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from semicon_alpha.graph.rules import load_graph_schema
from semicon_alpha.services.helpers import clean_record
from semicon_alpha.services.repository import WorldModelRepository
from semicon_alpha.settings import Settings


@dataclass(frozen=True)
class GraphTransition:
    edge_id: str
    edge_type: str
    source_node_id: str
    target_node_id: str
    weight: float
    confidence: float
    evidence: str | None
    reverse: bool
    multiplier: float


class GraphExplorerService:
    def __init__(self, settings: Settings, repo: WorldModelRepository) -> None:
        self.settings = settings
        self.repo = repo
        self.graph_schema = load_graph_schema(settings.configs_dir / "graph_schema.yaml")
        self.node_map = {
            row["node_id"]: clean_record(row)
            for row in self.repo.graph_nodes.to_dict(orient="records")
        }
        self.outgoing_map: dict[str, list[GraphTransition]] = defaultdict(list)
        self.incoming_map: dict[str, list[GraphTransition]] = defaultdict(list)
        for row in self.repo.graph_edges.to_dict(orient="records"):
            edge_type = str(row["edge_type"])
            rule = self.graph_schema.edge_type_rules.get(edge_type)
            forward_multiplier = rule.forward_multiplier if rule else 0.5
            reverse_multiplier = rule.reverse_multiplier if rule else 0.5
            allows_reverse = rule.allows_reverse_traversal if rule else True
            transition = GraphTransition(
                edge_id=str(row["edge_id"]),
                edge_type=edge_type,
                source_node_id=str(row["source_node_id"]),
                target_node_id=str(row["target_node_id"]),
                weight=float(row["weight"]),
                confidence=float(row["confidence"]),
                evidence=row.get("evidence"),
                reverse=False,
                multiplier=forward_multiplier,
            )
            self.outgoing_map[transition.source_node_id].append(transition)
            if allows_reverse:
                self.incoming_map[transition.target_node_id].append(
                    GraphTransition(
                        edge_id=transition.edge_id,
                        edge_type=edge_type,
                        source_node_id=transition.source_node_id,
                        target_node_id=transition.target_node_id,
                        weight=transition.weight,
                        confidence=transition.confidence,
                        evidence=transition.evidence,
                        reverse=True,
                        multiplier=reverse_multiplier,
                    )
                )

    def get_neighbors(
        self,
        node_id: str,
        relationship_types: list[str] | None = None,
        min_confidence: float = 0.0,
        max_items: int = 40,
    ) -> dict[str, Any]:
        allowed = set(relationship_types or [])
        outgoing = []
        incoming = []
        for edge in self.outgoing_map.get(node_id, []):
            if allowed and edge.edge_type not in allowed:
                continue
            if edge.confidence < min_confidence:
                continue
            outgoing.append(self._format_neighbor(edge, edge.target_node_id, "outgoing"))
        for edge in self.incoming_map.get(node_id, []):
            if allowed and edge.edge_type not in allowed:
                continue
            if edge.confidence < min_confidence:
                continue
            incoming.append(self._format_neighbor(edge, edge.source_node_id, "incoming"))
        outgoing.sort(key=lambda item: item["score_hint"], reverse=True)
        incoming.sort(key=lambda item: item["score_hint"], reverse=True)
        return {"node_id": node_id, "outgoing": outgoing[:max_items], "incoming": incoming[:max_items]}

    def trace_path(
        self,
        source_id: str,
        target_id: str,
        max_hops: int = 4,
        relationship_types: list[str] | None = None,
        min_confidence: float = 0.0,
        max_paths: int = 5,
    ) -> dict[str, Any]:
        if source_id not in self.node_map:
            raise KeyError(f"Unknown source node: {source_id}")
        if target_id not in self.node_map:
            raise KeyError(f"Unknown target node: {target_id}")

        allowed = set(relationship_types or [])
        queue = deque(
            [
                {
                    "node_id": source_id,
                    "nodes": [source_id],
                    "edges": [],
                    "score": 1.0,
                }
            ]
        )
        paths: list[dict[str, Any]] = []
        while queue:
            current = queue.popleft()
            current_node = current["node_id"]
            hop_count = len(current["edges"])
            if hop_count >= max_hops:
                continue
            transitions = [*self.outgoing_map.get(current_node, []), *self.incoming_map.get(current_node, [])]
            transitions.sort(key=lambda edge: edge.weight * edge.confidence * edge.multiplier, reverse=True)
            for edge in transitions:
                if allowed and edge.edge_type not in allowed:
                    continue
                if edge.confidence < min_confidence:
                    continue
                next_node = edge.source_node_id if edge.reverse else edge.target_node_id
                if next_node in current["nodes"]:
                    continue
                next_score = current["score"] * edge.weight * edge.confidence * edge.multiplier
                next_payload = {
                    "node_id": next_node,
                    "nodes": [*current["nodes"], next_node],
                    "edges": [
                        *current["edges"],
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
                    "score": next_score,
                }
                if next_node == target_id:
                    paths.append(
                        {
                            "path_nodes": next_payload["nodes"],
                            "path_labels": [self._node_label(node_id) for node_id in next_payload["nodes"]],
                            "path_edges": next_payload["edges"],
                            "hop_count": len(next_payload["edges"]),
                            "score": round(next_score, 4),
                        }
                    )
                else:
                    queue.append(next_payload)

        paths.sort(key=lambda item: item["score"], reverse=True)
        return {
            "source_id": source_id,
            "target_id": target_id,
            "source_label": self._node_label(source_id),
            "target_label": self._node_label(target_id),
            "paths": paths[:max_paths],
        }

    def _format_neighbor(self, edge: GraphTransition, other_node_id: str, direction: str) -> dict[str, Any]:
        return {
            "edge_id": edge.edge_id,
            "direction": direction,
            "edge_type": edge.edge_type,
            "other_node_id": other_node_id,
            "other_node_label": self._node_label(other_node_id),
            "other_node_type": self.node_map.get(other_node_id, {}).get("node_type"),
            "weight": round(edge.weight, 4),
            "confidence": round(edge.confidence, 4),
            "traversal": "reverse" if edge.reverse else "forward",
            "evidence": edge.evidence,
            "score_hint": round(edge.weight * edge.confidence * edge.multiplier, 4),
        }

    def _node_label(self, node_id: str) -> str:
        node = self.node_map.get(node_id)
        if not node:
            return node_id
        return str(node.get("label") or node_id)
