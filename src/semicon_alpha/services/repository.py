from __future__ import annotations

from functools import cached_property
from pathlib import Path

import pandas as pd

from semicon_alpha.settings import Settings


class WorldModelRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _read_parquet(self, name: str, required: bool = False) -> pd.DataFrame:
        path = self.settings.processed_dir / name
        if not path.exists():
            if required:
                raise FileNotFoundError(f"Required dataset missing: {path}")
            return pd.DataFrame()
        return pd.read_parquet(path)

    @cached_property
    def events(self) -> pd.DataFrame:
        frame = self._read_parquet("news_events_structured.parquet", required=True)
        if not frame.empty and "published_at_utc" in frame.columns:
            frame = frame.sort_values("published_at_utc", ascending=False).reset_index(drop=True)
        return frame

    @cached_property
    def event_scores(self) -> pd.DataFrame:
        return self._read_parquet("event_impact_scores.parquet")

    @cached_property
    def copilot_llm_responses(self) -> pd.DataFrame:
        return self._read_parquet("copilot_llm_responses.parquet")

    @cached_property
    def report_llm_generations(self) -> pd.DataFrame:
        return self._read_parquet("report_llm_generations.parquet")

    @cached_property
    def event_llm_reviews(self) -> pd.DataFrame:
        return self._read_parquet("event_llm_reviews.parquet")

    @cached_property
    def event_llm_entities(self) -> pd.DataFrame:
        return self._read_parquet("event_llm_entities.parquet")

    @cached_property
    def event_llm_themes(self) -> pd.DataFrame:
        return self._read_parquet("event_llm_themes.parquet")

    @cached_property
    def event_llm_fusion_decisions(self) -> pd.DataFrame:
        return self._read_parquet("event_llm_fusion_decisions.parquet")

    @cached_property
    def event_reactions(self) -> pd.DataFrame:
        return self._read_parquet("event_market_reactions.parquet")

    @cached_property
    def event_themes(self) -> pd.DataFrame:
        return self._read_parquet("news_event_themes.parquet")

    @cached_property
    def event_classifications(self) -> pd.DataFrame:
        return self._read_parquet("news_event_classifications.parquet")

    @cached_property
    def event_influences(self) -> pd.DataFrame:
        return self._read_parquet("event_node_influence.parquet")

    @cached_property
    def event_paths(self) -> pd.DataFrame:
        return self._read_parquet("event_propagation_paths.parquet")

    @cached_property
    def graph_nodes(self) -> pd.DataFrame:
        return self._read_parquet("graph_nodes.parquet", required=True)

    @cached_property
    def graph_edges(self) -> pd.DataFrame:
        return self._read_parquet("graph_edges.parquet", required=True)

    @cached_property
    def graph_node_history(self) -> pd.DataFrame:
        return self._read_parquet("graph_node_history.parquet")

    @cached_property
    def graph_edge_history(self) -> pd.DataFrame:
        return self._read_parquet("graph_edge_history.parquet")

    @cached_property
    def graph_change_log(self) -> pd.DataFrame:
        return self._read_parquet("graph_change_log.parquet")

    @cached_property
    def company_registry(self) -> pd.DataFrame:
        return self._read_parquet("company_registry.parquet", required=True)

    @cached_property
    def theme_nodes(self) -> pd.DataFrame:
        return self._read_parquet("theme_nodes.parquet")

    @cached_property
    def ontology_nodes(self) -> pd.DataFrame:
        return self._read_parquet("ontology_nodes.parquet")

    @cached_property
    def articles_enriched(self) -> pd.DataFrame:
        return self._read_parquet("news_articles_enriched.parquet")

    @cached_property
    def articles_discovered(self) -> pd.DataFrame:
        return self._read_parquet("news_articles_discovered.parquet")

    @cached_property
    def company_relationships(self) -> pd.DataFrame:
        return self._read_parquet("company_relationships.parquet")

    @cached_property
    def theme_relationships(self) -> pd.DataFrame:
        return self._read_parquet("theme_relationships.parquet")

    @cached_property
    def ontology_relationships(self) -> pd.DataFrame:
        return self._read_parquet("ontology_relationships.parquet")

    @cached_property
    def lag_predictions(self) -> pd.DataFrame:
        return self._read_parquet("event_lag_predictions.parquet")

    @cached_property
    def evaluation_summary(self) -> pd.DataFrame:
        return self._read_parquet("evaluation_summary.parquet")

    @cached_property
    def retrieval_index(self) -> pd.DataFrame:
        return self._read_parquet("retrieval_index.parquet")

    @cached_property
    def retrieval_embeddings(self) -> pd.DataFrame:
        return self._read_parquet("retrieval_embeddings.parquet")

    def invalidate(self) -> None:
        for attribute in list(vars(self)):
            if attribute.startswith("_"):
                continue
        for attribute in (
            "events",
            "event_scores",
            "copilot_llm_responses",
            "report_llm_generations",
            "event_llm_reviews",
            "event_llm_entities",
            "event_llm_themes",
            "event_llm_fusion_decisions",
            "event_reactions",
            "event_themes",
            "event_classifications",
            "event_influences",
            "event_paths",
            "graph_nodes",
            "graph_edges",
            "graph_node_history",
            "graph_edge_history",
            "graph_change_log",
            "company_registry",
            "theme_nodes",
            "ontology_nodes",
            "articles_enriched",
            "articles_discovered",
            "company_relationships",
            "theme_relationships",
            "ontology_relationships",
            "lag_predictions",
            "evaluation_summary",
            "retrieval_index",
            "retrieval_embeddings",
        ):
            self.__dict__.pop(attribute, None)


def discover_ui_root(current_file: Path) -> Path:
    return current_file.resolve().parents[1] / "ui" / "terminal"
