from __future__ import annotations

from collections import defaultdict
import json
from typing import Any

import pandas as pd

from semicon_alpha.models.records import (
    GraphChangeRecord,
    GraphEdgeHistoryRecord,
    GraphEdgeRecord,
    GraphNodeHistoryRecord,
    GraphNodeRecord,
)
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import now_utc, slugify, stable_id, upsert_parquet


class GraphBuildService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.catalog = DuckDBCatalog(settings)
        self.company_registry_path = settings.processed_dir / "company_registry.parquet"
        self.theme_nodes_path = settings.processed_dir / "theme_nodes.parquet"
        self.ontology_nodes_path = settings.processed_dir / "ontology_nodes.parquet"
        self.company_relationships_path = settings.processed_dir / "company_relationships.parquet"
        self.theme_relationships_path = settings.processed_dir / "theme_relationships.parquet"
        self.ontology_relationships_path = settings.processed_dir / "ontology_relationships.parquet"
        self.graph_nodes_path = settings.processed_dir / "graph_nodes.parquet"
        self.graph_edges_path = settings.processed_dir / "graph_edges.parquet"
        self.graph_node_history_path = settings.processed_dir / "graph_node_history.parquet"
        self.graph_edge_history_path = settings.processed_dir / "graph_edge_history.parquet"
        self.graph_change_log_path = settings.processed_dir / "graph_change_log.parquet"

    def run(self) -> dict[str, int]:
        company_frame = _read_required_parquet(self.company_registry_path)
        theme_frame = _read_required_parquet(self.theme_nodes_path)
        ontology_frame = _read_optional_parquet(self.ontology_nodes_path)
        company_edge_frame = _read_optional_parquet(self.company_relationships_path)
        theme_edge_frame = _read_optional_parquet(self.theme_relationships_path)
        ontology_edge_frame = _read_optional_parquet(self.ontology_relationships_path)
        previous_nodes = _read_optional_parquet(self.graph_nodes_path)
        previous_edges = _read_optional_parquet(self.graph_edges_path)

        processed_at = now_utc()
        snapshot_id = stable_id("graph_snapshot", processed_at.isoformat())
        ontology_frame = self._merge_country_ontology(company_frame, ontology_frame)

        nodes = (
            self._build_company_nodes(company_frame, processed_at)
            + self._build_theme_nodes(theme_frame, processed_at)
            + self._build_ontology_nodes(ontology_frame, processed_at)
            + self._derive_segment_nodes(company_frame, processed_at)
        )
        edges = (
            self._build_existing_edges(company_edge_frame, "company_relationships")
            + self._build_existing_edges(theme_edge_frame, "theme_relationships")
            + self._build_existing_edges(ontology_edge_frame, "ontology_relationships")
            + self._build_segment_membership_edges(company_frame)
            + self._build_country_membership_edges(company_frame, ontology_frame, ontology_edge_frame)
        )

        current_nodes = upsert_parquet(
            self.graph_nodes_path,
            nodes,
            unique_keys=["node_id"],
            sort_by=["node_type", "node_id", "created_at_utc"],
        )
        current_edges = upsert_parquet(
            self.graph_edges_path,
            edges,
            unique_keys=["edge_id"],
            sort_by=["source_node_id", "target_node_id", "edge_type"],
        )

        node_history = self._build_node_history(current_nodes, snapshot_id, processed_at)
        edge_history = self._build_edge_history(current_edges, snapshot_id, processed_at)
        change_log = self._build_change_log(
            previous_nodes=previous_nodes,
            previous_edges=previous_edges,
            current_nodes=current_nodes,
            current_edges=current_edges,
            snapshot_id=snapshot_id,
            snapshot_at=processed_at,
        )

        upsert_parquet(
            self.graph_node_history_path,
            node_history,
            unique_keys=["snapshot_id", "node_id"],
            sort_by=["snapshot_at_utc", "node_type", "node_id"],
        )
        upsert_parquet(
            self.graph_edge_history_path,
            edge_history,
            unique_keys=["snapshot_id", "edge_id"],
            sort_by=["snapshot_at_utc", "source_node_id", "target_node_id", "edge_type"],
        )
        upsert_parquet(
            self.graph_change_log_path,
            change_log,
            unique_keys=["snapshot_id", "object_type", "object_id"],
            sort_by=["snapshot_at_utc", "object_type", "object_id"],
        )
        self.catalog.refresh_processed_views()
        return {
            "node_count": len(current_nodes),
            "edge_count": len(current_edges),
            "node_history_count": len(node_history),
            "edge_history_count": len(edge_history),
            "change_count": len(change_log),
        }

    def _build_company_nodes(self, company_frame: pd.DataFrame, processed_at) -> list[GraphNodeRecord]:
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

    def _build_ontology_nodes(self, ontology_frame: pd.DataFrame, processed_at) -> list[GraphNodeRecord]:
        if ontology_frame.empty:
            return []
        nodes: list[GraphNodeRecord] = []
        for row in ontology_frame.to_dict(orient="records"):
            metadata = _parse_json_object(row.get("metadata_json"))
            aliases = _parse_json_list(row.get("aliases"))
            if aliases:
                metadata["aliases"] = aliases
            nodes.append(
                GraphNodeRecord(
                    node_id=row["node_id"],
                    node_type=row["node_type"],
                    label=row["label"],
                    description=row.get("description"),
                    source_table="ontology_nodes",
                    metadata_json=metadata,
                    is_active=bool(row.get("is_active", True)),
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

    def _build_existing_edges(self, edge_frame: pd.DataFrame, source_table: str) -> list[GraphEdgeRecord]:
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
                    last_updated=_coerce_str(row.get("last_updated")) or str(now_utc().date()),
                    effective_start=_coerce_str(row.get("effective_start")),
                    effective_end=_coerce_str(row.get("effective_end")),
                    relationship_status=_coerce_str(row.get("relationship_status")) or "active",
                    source_table=source_table,
                    is_derived=False,
                    metadata_json=_parse_json_object(row.get("metadata_json")) or None,
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
                        metadata_json={"membership": "primary"},
                    )
                )
            for secondary_segment in _parse_json_list(row.get("segment_secondary")):
                edges.append(
                    GraphEdgeRecord(
                        edge_id=stable_id("graph_edge", company_id, "segment", secondary_segment, "secondary"),
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
                        metadata_json={"membership": "secondary"},
                    )
                )
        return edges

    def _build_country_membership_edges(
        self,
        company_frame: pd.DataFrame,
        ontology_frame: pd.DataFrame,
        ontology_edge_frame: pd.DataFrame,
    ) -> list[GraphEdgeRecord]:
        country_nodes = {
            str(row["label"]).strip().lower(): row["node_id"]
            for row in ontology_frame.to_dict(orient="records")
            if str(row.get("node_type")) == "country"
        }
        explicit_edges = {
            (
                str(row["source_id"]),
                str(row["target_id"]),
                str(row["edge_type"]),
            )
            for row in ontology_edge_frame.to_dict(orient="records")
        }
        edges: list[GraphEdgeRecord] = []
        last_updated = str(now_utc().date())
        for row in company_frame.to_dict(orient="records"):
            country_name = str(row.get("country") or "").strip()
            if not country_name:
                continue
            country_node_id = country_nodes.get(country_name.lower(), f"country:{slugify(country_name)}")
            if (row["entity_id"], country_node_id, "located_in") in explicit_edges:
                continue
            edges.append(
                GraphEdgeRecord(
                    edge_id=stable_id("graph_edge", row["entity_id"], country_node_id, "located_in"),
                    source_node_id=row["entity_id"],
                    target_node_id=country_node_id,
                    source_node_type="company",
                    target_node_type="country",
                    edge_type="located_in",
                    weight=1.0,
                    sign="positive",
                    confidence=0.99,
                    evidence=f"{row['ticker']} is associated with {country_name}.",
                    last_updated=last_updated,
                    source_table="company_registry",
                    is_derived=True,
                    metadata_json={"derivation": "company_country"},
                )
            )
        return edges

    def _merge_country_ontology(self, company_frame: pd.DataFrame, ontology_frame: pd.DataFrame) -> pd.DataFrame:
        rows = [row.copy() for row in ontology_frame.to_dict(orient="records")] if not ontology_frame.empty else []
        existing_country_labels = {
            str(row.get("label")).strip().lower()
            for row in rows
            if str(row.get("node_type")) == "country"
        }
        for country_name in sorted({str(value).strip() for value in company_frame["country"].dropna().tolist() if str(value).strip()}):
            if country_name.lower() in existing_country_labels:
                continue
            rows.append(
                {
                    "node_id": f"country:{slugify(country_name)}",
                    "node_type": "country",
                    "label": country_name,
                    "description": f"Derived country node for tracked companies in {country_name}.",
                    "aliases": json.dumps([]),
                    "metadata_json": json.dumps({"derived": True}),
                    "is_active": True,
                }
            )
        return pd.DataFrame(rows)

    def _build_node_history(
        self,
        current_nodes: pd.DataFrame,
        snapshot_id: str,
        snapshot_at,
    ) -> list[GraphNodeHistoryRecord]:
        records: list[GraphNodeHistoryRecord] = []
        for row in current_nodes.to_dict(orient="records"):
            records.append(
                GraphNodeHistoryRecord(
                    snapshot_id=snapshot_id,
                    snapshot_at_utc=snapshot_at,
                    node_id=row["node_id"],
                    node_type=row["node_type"],
                    label=row["label"],
                    description=row.get("description"),
                    source_table=row["source_table"],
                    ticker=row.get("ticker"),
                    segment_primary=row.get("segment_primary"),
                    metadata_json=_parse_json_object(row.get("metadata_json")) or None,
                    is_active=bool(row.get("is_active", True)),
                )
            )
        return records

    def _build_edge_history(
        self,
        current_edges: pd.DataFrame,
        snapshot_id: str,
        snapshot_at,
    ) -> list[GraphEdgeHistoryRecord]:
        records: list[GraphEdgeHistoryRecord] = []
        for row in current_edges.to_dict(orient="records"):
            records.append(
                GraphEdgeHistoryRecord(
                    snapshot_id=snapshot_id,
                    snapshot_at_utc=snapshot_at,
                    edge_id=row["edge_id"],
                    source_node_id=row["source_node_id"],
                    target_node_id=row["target_node_id"],
                    source_node_type=row["source_node_type"],
                    target_node_type=row["target_node_type"],
                    edge_type=row["edge_type"],
                    weight=float(row["weight"]),
                    sign=row["sign"],
                    confidence=float(row["confidence"]),
                    evidence=row.get("evidence"),
                    evidence_url=row.get("evidence_url"),
                    last_updated=row["last_updated"],
                    effective_start=_coerce_str(row.get("effective_start")),
                    effective_end=_coerce_str(row.get("effective_end")),
                    relationship_status=_coerce_str(row.get("relationship_status")) or "active",
                    source_table=row["source_table"],
                    is_derived=bool(row.get("is_derived", False)),
                    metadata_json=_parse_json_object(row.get("metadata_json")) or None,
                )
            )
        return records

    def _build_change_log(
        self,
        *,
        previous_nodes: pd.DataFrame,
        previous_edges: pd.DataFrame,
        current_nodes: pd.DataFrame,
        current_edges: pd.DataFrame,
        snapshot_id: str,
        snapshot_at,
    ) -> list[GraphChangeRecord]:
        node_changes = self._diff_frames(
            previous_nodes,
            current_nodes,
            key_column="node_id",
            ignore_columns={"created_at_utc"},
        )
        edge_changes = self._diff_frames(
            previous_edges,
            current_edges,
            key_column="edge_id",
            ignore_columns=set(),
        )

        records: list[GraphChangeRecord] = []
        for node_id, payload in node_changes.items():
            previous = payload.get("previous")
            current = payload.get("current")
            record = current or previous or {}
            change_type = payload["change_type"]
            records.append(
                GraphChangeRecord(
                    snapshot_id=snapshot_id,
                    snapshot_at_utc=snapshot_at,
                    object_type="node",
                    object_id=node_id,
                    change_type=change_type,
                    node_id=node_id,
                    node_type=record.get("node_type"),
                    label=record.get("label"),
                    summary=f"Node {change_type}: {record.get('label') or node_id}",
                    previous_value_json=previous,
                    current_value_json=current,
                )
            )
        for edge_id, payload in edge_changes.items():
            previous = payload.get("previous")
            current = payload.get("current")
            record = current or previous or {}
            change_type = payload["change_type"]
            summary = (
                f"Edge {change_type}: {record.get('source_node_id')} -> {record.get('target_node_id')}"
                f" ({record.get('edge_type')})"
            )
            records.append(
                GraphChangeRecord(
                    snapshot_id=snapshot_id,
                    snapshot_at_utc=snapshot_at,
                    object_type="edge",
                    object_id=edge_id,
                    change_type=change_type,
                    edge_id=edge_id,
                    edge_type=record.get("edge_type"),
                    source_node_id=record.get("source_node_id"),
                    target_node_id=record.get("target_node_id"),
                    summary=summary,
                    previous_value_json=previous,
                    current_value_json=current,
                )
            )
        return records

    def _diff_frames(
        self,
        previous: pd.DataFrame,
        current: pd.DataFrame,
        *,
        key_column: str,
        ignore_columns: set[str],
    ) -> dict[str, dict[str, Any]]:
        previous_map = _frame_to_map(previous, key_column=key_column, ignore_columns=ignore_columns)
        current_map = _frame_to_map(current, key_column=key_column, ignore_columns=ignore_columns)
        changes: dict[str, dict[str, Any]] = {}
        for object_id, current_row in current_map.items():
            if object_id not in previous_map:
                changes[object_id] = {"change_type": "added", "previous": None, "current": current_row}
                continue
            previous_row = previous_map[object_id]
            if previous_row != current_row:
                changes[object_id] = {
                    "change_type": "updated",
                    "previous": previous_row,
                    "current": current_row,
                }
        for object_id, previous_row in previous_map.items():
            if object_id not in current_map:
                changes[object_id] = {"change_type": "removed", "previous": previous_row, "current": None}
        return changes


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


def _parse_json_object(value) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): val for key, val in value.items()}
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return {}
        if value.startswith("{"):
            try:
                parsed = json.loads(value)
            except Exception:  # pragma: no cover - defensive for malformed data
                parsed = None
            if isinstance(parsed, dict):
                return {str(key): val for key, val in parsed.items()}
        return {"value": value}
    return {"value": value}


def _frame_to_map(
    frame: pd.DataFrame,
    *,
    key_column: str,
    ignore_columns: set[str],
) -> dict[str, dict[str, Any]]:
    if frame.empty or key_column not in frame.columns:
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for row in frame.to_dict(orient="records"):
        normalized = {
            key: _normalize_value(value)
            for key, value in row.items()
            if key not in ignore_columns
        }
        rows[str(row[key_column])] = normalized
    return rows


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except Exception:  # pragma: no cover - defensive
                return stripped
        return stripped
    if pd.isna(value):
        return None
    return value


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
