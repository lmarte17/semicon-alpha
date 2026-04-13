from __future__ import annotations

from collections import defaultdict
import json

import pandas as pd

from semicon_alpha.models.records import GraphEdgeRecord, GraphNodeRecord
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, stable_id, upsert_parquet


class GraphBuildService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.company_registry_path = settings.processed_dir / "company_registry.parquet"
        self.theme_nodes_path = settings.processed_dir / "theme_nodes.parquet"
        self.company_relationships_path = settings.processed_dir / "company_relationships.parquet"
        self.theme_relationships_path = settings.processed_dir / "theme_relationships.parquet"
        self.graph_nodes_path = settings.processed_dir / "graph_nodes.parquet"
        self.graph_edges_path = settings.processed_dir / "graph_edges.parquet"

    def run(self) -> dict[str, int]:
        company_frame = _read_required_parquet(self.company_registry_path)
        theme_frame = _read_required_parquet(self.theme_nodes_path)
        company_edge_frame = _read_optional_parquet(self.company_relationships_path)
        theme_edge_frame = _read_optional_parquet(self.theme_relationships_path)

        processed_at = now_utc()
        segment_nodes = self._derive_segment_nodes(company_frame, processed_at)
        nodes = (
            self._build_company_nodes(company_frame, processed_at)
            + self._build_theme_nodes(theme_frame, processed_at)
            + segment_nodes
        )
        edges = (
            self._build_existing_edges(company_edge_frame, "company_relationships")
            + self._build_existing_edges(theme_edge_frame, "theme_relationships")
            + self._build_segment_membership_edges(company_frame)
        )

        upsert_parquet(
            self.graph_nodes_path,
            nodes,
            unique_keys=["node_id"],
            sort_by=["node_type", "node_id", "created_at_utc"],
        )
        upsert_parquet(
            self.graph_edges_path,
            edges,
            unique_keys=["edge_id"],
            sort_by=["source_node_id", "target_node_id", "edge_type"],
        )
        self.catalog.refresh_processed_views()
        return {"node_count": len(nodes), "edge_count": len(edges)}

    def _build_company_nodes(
        self, company_frame: pd.DataFrame, processed_at
    ) -> list[GraphNodeRecord]:
        nodes: list[GraphNodeRecord] = []
        for row in company_frame.to_dict(orient="records"):
            nodes.append(
                GraphNodeRecord(
                    node_id=row["entity_id"],
                    node_type="company",
                    label=row["company_name"],
                    description=row.get("description") or row.get("notes"),
                    source_table="company_registry",
                    ticker=row["ticker"],
                    segment_primary=row["segment_primary"],
                    metadata_json={
                        "ecosystem_role": row.get("ecosystem_role"),
                        "country": row.get("country"),
                        "market_cap_bucket": row.get("market_cap_bucket"),
                        "segment_secondary": _parse_json_list(row.get("segment_secondary")),
                    },
                    is_active=True,
                    created_at_utc=processed_at,
                )
            )
        return nodes

    def _build_theme_nodes(self, theme_frame: pd.DataFrame, processed_at) -> list[GraphNodeRecord]:
        nodes: list[GraphNodeRecord] = []
        for row in theme_frame.to_dict(orient="records"):
            nodes.append(
                GraphNodeRecord(
                    node_id=row["node_id"],
                    node_type="theme",
                    label=row["theme_name"],
                    description=row.get("description"),
                    source_table="theme_nodes",
                    metadata_json={"node_category": row.get("node_category")},
                    is_active=True,
                    created_at_utc=processed_at,
                )
            )
        return nodes

    def _derive_segment_nodes(self, company_frame: pd.DataFrame, processed_at) -> list[GraphNodeRecord]:
        segment_descriptions: dict[str, str] = defaultdict(str)
        for row in company_frame.to_dict(orient="records"):
            primary = row.get("segment_primary")
            if primary:
                segment_descriptions[primary] = segment_descriptions[primary] or (
                    f"Derived segment node for companies with primary segment '{primary}'."
                )
            for secondary in _parse_json_list(row.get("segment_secondary")):
                segment_descriptions[secondary] = segment_descriptions[secondary] or (
                    f"Derived segment node for companies with secondary segment '{secondary}'."
                )
        nodes: list[GraphNodeRecord] = []
        for segment in sorted(segment_descriptions):
            nodes.append(
                GraphNodeRecord(
                    node_id=f"segment:{segment}",
                    node_type="segment",
                    label=segment.replace("_", " ").title(),
                    description=segment_descriptions[segment],
                    source_table="company_registry",
                    segment_primary=segment,
                    metadata_json={"segment_key": segment},
                    is_active=True,
                    created_at_utc=processed_at,
                )
            )
        return nodes

    def _build_existing_edges(
        self, edge_frame: pd.DataFrame, source_table: str
    ) -> list[GraphEdgeRecord]:
        if edge_frame.empty:
            return []
        edges: list[GraphEdgeRecord] = []
        for row in edge_frame.to_dict(orient="records"):
            edges.append(
                GraphEdgeRecord(
                    edge_id=row["edge_id"],
                    source_node_id=row["source_id"],
                    target_node_id=row["target_id"],
                    source_node_type=row["source_type"],
                    target_node_type=row["target_type"],
                    edge_type=row["edge_type"],
                    weight=float(row["weight"]),
                    sign=row["sign"],
                    confidence=float(row["confidence"]),
                    evidence=row.get("evidence"),
                    evidence_url=row.get("evidence_url"),
                    last_updated=row["last_updated"],
                    source_table=source_table,
                    is_derived=False,
                )
            )
        return edges

    def _build_segment_membership_edges(self, company_frame: pd.DataFrame) -> list[GraphEdgeRecord]:
        edges: list[GraphEdgeRecord] = []
        last_updated = str(now_utc().date())
        for row in company_frame.to_dict(orient="records"):
            company_id = row["entity_id"]
            ticker = row["ticker"]
            primary_segment = row.get("segment_primary")
            if primary_segment:
                edges.append(
                    GraphEdgeRecord(
                        edge_id=stable_id("graph_edge", company_id, "segment", primary_segment, "primary"),
                        source_node_id=company_id,
                        target_node_id=f"segment:{primary_segment}",
                        source_node_type="company",
                        target_node_type="segment",
                        edge_type="in_segment_primary",
                        weight=1.0,
                        sign="positive",
                        confidence=1.0,
                        evidence=f"{ticker} has primary segment {primary_segment}.",
                        last_updated=last_updated,
                        source_table="company_registry",
                        is_derived=True,
                    )
                )
            for secondary_segment in _parse_json_list(row.get("segment_secondary")):
                edges.append(
                    GraphEdgeRecord(
                        edge_id=stable_id(
                            "graph_edge",
                            company_id,
                            "segment",
                            secondary_segment,
                            "secondary",
                        ),
                        source_node_id=company_id,
                        target_node_id=f"segment:{secondary_segment}",
                        source_node_type="company",
                        target_node_type="segment",
                        edge_type="in_segment_secondary",
                        weight=0.8,
                        sign="positive",
                        confidence=0.95,
                        evidence=f"{ticker} has secondary segment {secondary_segment}.",
                        last_updated=last_updated,
                        source_table="company_registry",
                        is_derived=True,
                    )
                )
        return edges


def _read_required_parquet(path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Required parquet dataset missing: {path}")
    return pd.read_parquet(path)


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
            except Exception:  # pragma: no cover - defensive for malformed data
                parsed = None
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]
