from __future__ import annotations

from pathlib import Path

import networkx as nx
import pandas as pd


def build_multidigraph(graph_nodes_path: Path, graph_edges_path: Path) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    node_frame = pd.read_parquet(graph_nodes_path)
    edge_frame = pd.read_parquet(graph_edges_path)

    for row in node_frame.to_dict(orient="records"):
        graph.add_node(row["node_id"], **row)

    for row in edge_frame.to_dict(orient="records"):
        graph.add_edge(
            row["source_node_id"],
            row["target_node_id"],
            key=row["edge_id"],
            **row,
        )
    return graph


def get_neighbors(graph: nx.MultiDiGraph, node_id: str) -> dict[str, list[dict]]:
    outgoing = []
    incoming = []

    for _source, target, key, data in graph.out_edges(node_id, keys=True, data=True):
        outgoing.append(
            {
                "edge_id": key,
                "target_node_id": target,
                "edge_type": data.get("edge_type"),
                "weight": data.get("weight"),
                "confidence": data.get("confidence"),
                "sign": data.get("sign"),
            }
        )

    for source, _target, key, data in graph.in_edges(node_id, keys=True, data=True):
        incoming.append(
            {
                "edge_id": key,
                "source_node_id": source,
                "edge_type": data.get("edge_type"),
                "weight": data.get("weight"),
                "confidence": data.get("confidence"),
                "sign": data.get("sign"),
            }
        )

    return {"outgoing": outgoing, "incoming": incoming}
