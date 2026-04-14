from __future__ import annotations

import re
from typing import Any

from semicon_alpha.services.dashboard import DashboardService
from semicon_alpha.services.entities import EntityWorkspaceService
from semicon_alpha.services.events import EventWorkspaceService
from semicon_alpha.services.graph_view import GraphExplorerService
from semicon_alpha.services.scenarios import ScenarioService
from semicon_alpha.services.search import SearchService
from semicon_alpha.services.theses import ThesisService


class CopilotService:
    def __init__(
        self,
        dashboard_service: DashboardService,
        entity_service: EntityWorkspaceService,
        event_service: EventWorkspaceService,
        graph_service: GraphExplorerService,
        search_service: SearchService,
        scenario_service: ScenarioService,
        thesis_service: ThesisService,
    ) -> None:
        self.dashboard_service = dashboard_service
        self.entity_service = entity_service
        self.event_service = event_service
        self.graph_service = graph_service
        self.search_service = search_service
        self.scenario_service = scenario_service
        self.thesis_service = thesis_service

    def query(
        self,
        query: str,
        event_id: str | None = None,
        entity_id: str | None = None,
        scenario_id: str | None = None,
        thesis_id: str | None = None,
    ) -> dict[str, Any]:
        lowered = query.lower().strip()
        if event_id:
            return self._handle_event_scoped(query, lowered, event_id)
        if entity_id:
            return self._handle_entity_scoped(query, lowered, entity_id)
        if scenario_id:
            return self._handle_scenario_scoped(scenario_id)
        if thesis_id:
            return self._handle_thesis_scoped(thesis_id)

        compare_match = re.search(r"compare\s+(.+?)\s+and\s+(.+)", lowered)
        if compare_match:
            entity_a = self._resolve_entity(compare_match.group(1))
            entity_b = self._resolve_entity(compare_match.group(2))
            if entity_a and entity_b:
                return self._compare_entities(entity_a["id"], entity_b["id"])

        if "what changed" in lowered or "this week" in lowered:
            return self._weekly_summary()

        search_results = self.search_service.search(query, limit=5)
        answer = "No strong scoped interpretation was found. Returning the most relevant entities, events, and documents."
        observations = [
            f"{len(search_results['events'])} event matches",
            f"{len(search_results['entities'])} entity matches",
            f"{len(search_results['documents'])} document matches",
        ]
        return {
            "answer": answer,
            "observations": observations,
            "inferences": [],
            "citations": search_results["documents"][:3],
            "related_entities": search_results["entities"],
            "related_events": search_results["events"],
        }

    def _handle_event_scoped(self, query: str, lowered: str, event_id: str) -> dict[str, Any]:
        workspace = self.event_service.get_event_workspace(event_id)
        event = workspace["event"]
        impacts = workspace["impact_candidates"]
        target_entity = self._resolve_entity_from_query(query)
        if target_entity:
            entity_id = target_entity["id"]
            target_ticker = entity_id.split(":", 1)[1] if ":" in entity_id else entity_id
            impact = next((row for row in impacts if row["ticker"] == target_ticker), None)
            if impact:
                answer = (
                    f"{target_ticker} matters to this event because it is a {impact['impact_direction']} impact candidate "
                    f"with rank score {impact['total_rank_score']:.2f} and expected lag {impact['predicted_lag_bucket']}."
                )
                observations = [
                    f"Event: {event['headline']}",
                    f"Target company: {target_ticker}",
                    f"Best path count retained: {len(impact['top_paths'])}",
                ]
                inferences = [impact["explanation"]]
                citations = workspace["supporting_evidence"]["source_documents"]
                return {
                    "answer": answer,
                    "observations": observations,
                    "inferences": inferences,
                    "citations": citations,
                    "related_entities": [target_entity],
                    "related_events": [{"id": event_id, "title": event["headline"]}],
                }

        top_impacts = impacts[:3]
        answer = (
            f"{event['headline']} currently propagates most strongly into "
            + ", ".join(f"{row['ticker']} ({row['predicted_lag_bucket']})" for row in top_impacts)
            if top_impacts
            else f"{event['headline']} has limited ranked impact candidates so far."
        )
        observations = [
            f"Event type: {event['event_type']}",
            f"Direction / severity: {event['direction']} / {event['severity']}",
            f"Top theme count: {len(workspace['themes'])}",
        ]
        inferences = [row["explanation"] for row in top_impacts[:2] if row.get("explanation")]
        return {
            "answer": answer,
            "observations": observations,
            "inferences": inferences,
            "citations": workspace["supporting_evidence"]["source_documents"],
            "related_entities": [
                {"id": row["entity_id"], "title": row["ticker"], "type": "entity"} for row in top_impacts
            ],
            "related_events": [{"id": event_id, "title": event["headline"], "type": "event"}],
        }

    def _handle_entity_scoped(self, query: str, lowered: str, entity_id: str) -> dict[str, Any]:
        workspace = self.entity_service.get_entity_workspace(entity_id)
        entity = workspace["entity"]
        compare_match = re.search(r"compare\s+.+?\s+and\s+(.+)", lowered)
        if compare_match:
            other = self._resolve_entity(compare_match.group(1))
            if other:
                return self._compare_entities(entity_id, other["id"])

        answer = (
            f"{entity['label']} sits in the {entity.get('ecosystem_role') or entity['node_type']} role and "
            f"currently has {workspace['exposure_summary']['event_count']} linked scored events."
        )
        observations = [
            f"Primary segment: {entity.get('segment_primary')}",
            f"Recent linked events: {len(workspace['recent_events'])}",
            f"Outgoing neighbors: {len(workspace['neighbors']['outgoing'])}",
        ]
        inferences = []
        if workspace["effect_pathways"]:
            inferences.append(workspace["effect_pathways"][0]["explanation"])
        return {
            "answer": answer,
            "observations": observations,
            "inferences": [item for item in inferences if item],
            "citations": workspace["evidence"]["linked_events"][:3],
            "related_entities": [],
            "related_events": [
                {"id": row["event_id"], "title": row["headline"], "type": "event"}
                for row in workspace["recent_events"][:5]
                if row.get("headline")
            ],
        }

    def _handle_scenario_scoped(self, scenario_id: str) -> dict[str, Any]:
        workspace = self.scenario_service.get_scenario_workspace(scenario_id)
        scenario = workspace["scenario"]
        latest_run = workspace["latest_run"] or self.scenario_service.run_scenario(scenario_id)
        impacted = latest_run.get("impacted_entities_json") or []
        leaders = ", ".join(
            f"{row['ticker']} ({row['direction']})"
            for row in impacted[:3]
            if row.get("ticker")
        )
        answer = (
            f"{scenario['name']} currently points most strongly toward {leaders or 'no clear affected entities'} "
            "based on its explicit assumptions and retained graph paths."
        )
        observations = [
            f"Assumption count: {len(workspace['assumptions'])}",
            f"Monitor count: {len(workspace['monitors'])}",
            f"Run history count: {len(workspace['run_history'])}",
        ]
        inferences = [latest_run.get("run_summary")] if latest_run.get("run_summary") else []
        return {
            "answer": answer,
            "observations": observations,
            "inferences": inferences,
            "citations": [],
            "related_entities": [
                {"id": row["entity_id"], "title": row["label"], "type": "entity"} for row in impacted[:5]
            ],
            "related_events": [
                {"id": row["event_id"], "title": row["headline"], "type": "event"}
                for row in workspace["contradiction_signals"][:3] + workspace["support_signals"][:3]
                if row.get("event_id")
            ],
        }

    def _handle_thesis_scoped(self, thesis_id: str) -> dict[str, Any]:
        workspace = self.thesis_service.get_thesis_workspace(thesis_id)
        thesis = workspace["thesis"]
        answer = (
            f"{thesis['title']} is currently {thesis.get('stance')} with confidence "
            f"{float(thesis.get('confidence') or 0.0):.2f}. "
            f"There are {len(workspace['support_signals'])} supportive signals and "
            f"{len(workspace['contradiction_signals'])} contradictory signals in the current monitor set."
        )
        observations = [
            f"Linked items: {len(workspace['links'])}",
            f"Update count: {len(workspace['updates'])}",
            f"Status: {thesis.get('status')}",
        ]
        inferences = [workspace["updates"][0]["summary"]] if workspace["updates"] else []
        return {
            "answer": answer,
            "observations": observations,
            "inferences": inferences,
            "citations": [],
            "related_entities": [],
            "related_events": [
                {"id": row["event_id"], "title": row["headline"], "type": "event"}
                for row in workspace["support_signals"][:3] + workspace["contradiction_signals"][:3]
                if row.get("event_id")
            ],
        }

    def _compare_entities(self, entity_a_id: str, entity_b_id: str) -> dict[str, Any]:
        left = self.entity_service.get_entity_workspace(entity_a_id)
        right = self.entity_service.get_entity_workspace(entity_b_id)
        left_entity = left["entity"]
        right_entity = right["entity"]
        answer = (
            f"{left_entity['label']} and {right_entity['label']} differ most in ecosystem role and current event exposure. "
            f"{left_entity['label']} has {left['exposure_summary']['event_count']} linked events versus "
            f"{right['exposure_summary']['event_count']} for {right_entity['label']}."
        )
        observations = [
            f"{left_entity['label']}: {left_entity.get('ecosystem_role')} / {left_entity.get('segment_primary')}",
            f"{right_entity['label']}: {right_entity.get('ecosystem_role')} / {right_entity.get('segment_primary')}",
        ]
        inferences = [
            f"{left_entity['label']} avg rank score: {left['exposure_summary']['avg_rank_score']}",
            f"{right_entity['label']} avg rank score: {right['exposure_summary']['avg_rank_score']}",
        ]
        return {
            "answer": answer,
            "observations": observations,
            "inferences": inferences,
            "citations": [],
            "related_entities": [
                {"id": entity_a_id, "title": left_entity["label"], "type": "entity"},
                {"id": entity_b_id, "title": right_entity["label"], "type": "entity"},
            ],
            "related_events": [],
        }

    def _weekly_summary(self) -> dict[str, Any]:
        overview = self.dashboard_service.get_overview(limit=5)
        recent_events = overview["recent_events"][:5]
        answer = (
            "Recent notable events center on "
            + ", ".join(event["event_type"] for event in recent_events[:3])
            if recent_events
            else "No recent events are currently available."
        )
        observations = [event["headline"] for event in recent_events[:3]]
        inferences = [
            ", ".join(
                f"{impact['ticker']} ({impact['predicted_lag_bucket']})"
                for impact in event["top_impacts"][:3]
            )
            for event in recent_events[:2]
            if event["top_impacts"]
        ]
        return {
            "answer": answer,
            "observations": observations,
            "inferences": inferences,
            "citations": [],
            "related_entities": [],
            "related_events": [
                {"id": row["event_id"], "title": row["headline"], "type": "event"} for row in recent_events
            ],
        }

    def _resolve_entity_from_query(self, query: str) -> dict[str, Any] | None:
        search = self.search_service.search(query, limit=5)
        return search["entities"][0] if search["entities"] else None

    def _resolve_entity(self, query: str) -> dict[str, Any] | None:
        search = self.search_service.search(query, limit=5)
        return search["entities"][0] if search["entities"] else None
