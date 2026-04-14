from __future__ import annotations

from typing import Iterable

import pandas as pd

from semicon_alpha.ingestion.fmp import FMPIngestionService
from semicon_alpha.models.records import (
    CompanyFundamentalRecord,
    CompanyRegistryRecord,
    OntologyNodeRecord,
    RelationshipEdgeRecord,
    ThemeNodeRecord,
    UniverseCompanyConfig,
)
from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import load_yaml, now_utc, upsert_parquet


class ReferenceDataService:
    def __init__(self, settings: Settings, market_service: FMPIngestionService) -> None:
        self.settings = settings
        self.market_service = market_service
        self.catalog = DuckDBCatalog(settings)
        self.company_registry_path = settings.processed_dir / "company_registry.parquet"
        self.theme_nodes_path = settings.processed_dir / "theme_nodes.parquet"
        self.ontology_nodes_path = settings.processed_dir / "ontology_nodes.parquet"
        self.company_relationships_path = settings.processed_dir / "company_relationships.parquet"
        self.theme_relationships_path = settings.processed_dir / "theme_relationships.parquet"
        self.ontology_relationships_path = settings.processed_dir / "ontology_relationships.parquet"

    def sync_reference_data(self, skip_exchange_symbols: bool = False) -> dict[str, int]:
        companies = self.market_service.load_universe()
        themes = self.load_themes()
        ontology_nodes = self.load_ontology_nodes()
        relationships = self.load_relationships()

        if not skip_exchange_symbols:
            exchange_codes = {company.exchange for company in companies}
            self.market_service.sync_exchange_symbols(exchange_codes)

        fundamentals = self.market_service.sync_company_fundamentals(companies)
        company_registry = self.build_company_registry(companies, fundamentals)
        (
            company_relationships,
            theme_relationships,
            ontology_relationships,
        ) = self.partition_relationships(relationships)

        upsert_parquet(self.company_registry_path, company_registry, unique_keys=["entity_id"])
        upsert_parquet(self.theme_nodes_path, themes, unique_keys=["node_id"])
        upsert_parquet(self.ontology_nodes_path, ontology_nodes, unique_keys=["node_id"])
        upsert_parquet(
            self.company_relationships_path,
            company_relationships,
            unique_keys=["edge_id"],
        )
        upsert_parquet(
            self.theme_relationships_path,
            theme_relationships,
            unique_keys=["edge_id"],
        )
        upsert_parquet(
            self.ontology_relationships_path,
            ontology_relationships,
            unique_keys=["edge_id"],
        )
        self.catalog.refresh_processed_views()
        return {
            "company_count": len(company_registry),
            "theme_count": len(themes),
            "ontology_node_count": len(ontology_nodes),
            "relationship_count": len(relationships),
            "fundamental_count": len(fundamentals),
        }

    def load_themes(self) -> list[ThemeNodeRecord]:
        payload = load_yaml(self.settings.configs_dir / "theme_nodes.yaml")
        return [ThemeNodeRecord(**item) for item in payload["themes"]]

    def load_ontology_nodes(self) -> list[OntologyNodeRecord]:
        payload = load_yaml(self.settings.configs_dir / "ontology_nodes.yaml")
        return [OntologyNodeRecord(**item) for item in payload["nodes"]]

    def load_relationships(self) -> list[RelationshipEdgeRecord]:
        payload = load_yaml(self.settings.configs_dir / "relationship_edges.yaml")
        return [RelationshipEdgeRecord(**item) for item in payload["edges"]]

    def build_company_registry(
        self,
        companies: Iterable[UniverseCompanyConfig],
        fundamentals: list[CompanyFundamentalRecord],
    ) -> list[CompanyRegistryRecord]:
        fundamental_map = {record.ticker: record for record in fundamentals}
        updated_at = now_utc()
        registry: list[CompanyRegistryRecord] = []
        for company in companies:
            fundamental = fundamental_map.get(company.ticker)
            registry.append(
                CompanyRegistryRecord(
                    entity_id=f"company:{company.ticker}",
                    ticker=company.ticker,
                    eodhd_symbol=company.eodhd_symbol,
                    company_name=fundamental.company_name if fundamental and fundamental.company_name else company.company_name,
                    exchange=fundamental.exchange if fundamental and fundamental.exchange else company.exchange,
                    country=fundamental.country if fundamental and fundamental.country else company.country,
                    segment_primary=company.segment_primary,
                    segment_secondary=company.segment_secondary,
                    ecosystem_role=company.ecosystem_role,
                    market_cap_bucket=company.market_cap_bucket,
                    is_origin_name_candidate=company.is_origin_name_candidate,
                    notes=company.notes,
                    sector=fundamental.sector if fundamental else None,
                    industry=fundamental.industry if fundamental else None,
                    description=fundamental.description if fundamental else None,
                    website=fundamental.website if fundamental else None,
                    isin=fundamental.isin if fundamental else None,
                    lei=fundamental.lei if fundamental else None,
                    cik=fundamental.cik if fundamental else None,
                    reference_last_updated=updated_at,
                )
            )
        return registry

    def partition_relationships(
        self, relationships: Iterable[RelationshipEdgeRecord]
    ) -> tuple[list[RelationshipEdgeRecord], list[RelationshipEdgeRecord], list[RelationshipEdgeRecord]]:
        company_edges: list[RelationshipEdgeRecord] = []
        theme_edges: list[RelationshipEdgeRecord] = []
        ontology_edges: list[RelationshipEdgeRecord] = []
        for relationship in relationships:
            if relationship.source_type == "company" and relationship.target_type == "company":
                company_edges.append(relationship)
            elif "theme" in {relationship.source_type, relationship.target_type}:
                theme_edges.append(relationship)
            else:
                ontology_edges.append(relationship)
        return company_edges, theme_edges, ontology_edges


def load_company_registry_frame(path) -> pd.DataFrame:
    return pd.read_parquet(path)
