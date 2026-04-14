from __future__ import annotations

from pathlib import Path
from typing import Any

from semicon_alpha.appstate import AppStateRepository
from semicon_alpha.llm.workflows import AnalystSynthesisService
from semicon_alpha.services.boards import BoardService
from semicon_alpha.services.dashboard import DashboardService
from semicon_alpha.services.entities import EntityWorkspaceService
from semicon_alpha.services.events import EventWorkspaceService
from semicon_alpha.services.research import ResearchService
from semicon_alpha.services.scenarios import ScenarioService
from semicon_alpha.settings import Settings
from semicon_alpha.services.theses import ThesisService


class ReportService:
    def __init__(
        self,
        settings: Settings,
        appstate: AppStateRepository,
        dashboard_service: DashboardService,
        event_service: EventWorkspaceService,
        entity_service: EntityWorkspaceService,
        board_service: BoardService,
        research_service: ResearchService,
        scenario_service: ScenarioService,
        thesis_service: ThesisService,
        synthesis_service: AnalystSynthesisService | None = None,
    ) -> None:
        self.settings = settings
        self.appstate = appstate
        self.dashboard_service = dashboard_service
        self.event_service = event_service
        self.entity_service = entity_service
        self.board_service = board_service
        self.research_service = research_service
        self.scenario_service = scenario_service
        self.thesis_service = thesis_service
        self.synthesis_service = synthesis_service or AnalystSynthesisService(settings)

    def list_reports(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.appstate.list_reports(limit=limit)

    def get_report(self, report_id: str) -> dict[str, Any]:
        report = self.appstate.get_report(report_id)
        if report is None:
            raise KeyError(f"Unknown report_id: {report_id}")
        return report

    def generate_report(
        self,
        report_type: str,
        event_id: str | None = None,
        entity_id: str | None = None,
        compare_entity_id: str | None = None,
        board_id: str | None = None,
        scenario_id: str | None = None,
        thesis_id: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any]
        if report_type == "event_impact_brief":
            if not event_id:
                raise KeyError("event_id is required for event_impact_brief")
            payload = self._event_impact_brief(event_id)
        elif report_type == "weekly_thematic_brief":
            payload = self._weekly_thematic_brief(query=query, board_id=board_id)
        elif report_type == "entity_comparison_brief":
            if not entity_id or not compare_entity_id:
                raise KeyError("entity_id and compare_entity_id are required for entity_comparison_brief")
            payload = self._entity_comparison_brief(entity_id, compare_entity_id)
        elif report_type == "scenario_memo":
            if not scenario_id:
                raise KeyError("scenario_id is required for scenario_memo")
            payload = self._scenario_memo(scenario_id)
        elif report_type == "thesis_change_report":
            if not thesis_id:
                raise KeyError("thesis_id is required for thesis_change_report")
            payload = self._thesis_change_report(thesis_id)
        else:
            raise KeyError(f"Unsupported report type: {report_type}")

        if self.settings.llm_runtime_enabled:
            synthesis = self.synthesis_service.synthesize_report(
                report_type=report_type,
                title=payload["title"],
                scope_type=payload.get("scope_type"),
                scope_id=payload.get("scope_id"),
                deterministic_payload=payload,
            )
            payload["summary"] = synthesis.summary
            payload["markdown"] = synthesis.markdown
            payload["citations"] = synthesis.citations
            payload["llm_synthesis"] = {
                "observations": synthesis.payload["observations"],
                "inferences": synthesis.payload["inferences"],
                "uncertainties": synthesis.payload["uncertainties"],
                "next_checks": synthesis.payload["next_checks"],
                "synthesis_status": synthesis.record_fields["synthesis_status"],
                "model_name": synthesis.record_fields["model_name"],
                "confidence": synthesis.record_fields["confidence"],
            }
        else:
            synthesis = None

        report = self.appstate.create_report(
            report_type=report_type,
            title=payload["title"],
            summary=payload["summary"],
            scope_type=payload.get("scope_type"),
            scope_id=payload.get("scope_id"),
            citations=payload.get("citations", []),
            payload=payload,
            markdown=payload["markdown"],
        )
        if synthesis is not None:
            self.synthesis_service.persist_report_generation(
                report_id=report["report_id"],
                result=synthesis,
            )
        self._export_markdown(report)
        return report

    def _event_impact_brief(self, event_id: str) -> dict[str, Any]:
        workspace = self.event_service.get_event_workspace(event_id)
        analogs = self.research_service.get_event_analogs(event_id, limit=5)
        backtest = self.research_service.get_event_backtest(event_id)
        event = workspace["event"]
        top_impacts = workspace["impact_candidates"][:5]
        citations = workspace["supporting_evidence"]["source_documents"]
        markdown = "\n".join(
            [
                f"# Event Impact Brief: {event['headline']}",
                "",
                f"- Event type: {event.get('event_type')}",
                f"- Direction / severity: {event.get('direction')} / {event.get('severity')}",
                f"- Source: {event.get('source')}",
                "",
                "## What matters",
                workspace["event"].get("summary") or "No summary available.",
                "",
                "## Top impact candidates",
                *[
                    f"- {row['ticker']}: {row['impact_direction']} | lag {row['predicted_lag_bucket']} | score {row['total_rank_score']:.2f}"
                    for row in top_impacts
                ],
                "",
                "## Historical analogs",
                *[
                    f"- {row['headline']} ({row['similarity_score']:.2f}): {', '.join(row['similarity_reasons'])}"
                    for row in analogs
                ],
                "",
                "## Backtest snapshot",
                f"- Candidate count: {backtest['summary']['candidate_count']}",
                f"- Hit count: {backtest['summary']['hit_count']}",
            ]
        )
        return {
            "title": f"Event Impact Brief: {event['headline']}",
            "summary": event.get("summary") or "Event impact brief",
            "scope_type": "event",
            "scope_id": event_id,
            "citations": citations,
            "sections": {
                "event": event,
                "top_impacts": top_impacts,
                "analogs": analogs,
                "backtest": backtest,
            },
            "markdown": markdown,
        }

    def _weekly_thematic_brief(self, query: str | None = None, board_id: str | None = None) -> dict[str, Any]:
        overview = self.dashboard_service.get_overview(limit=8)
        board = self.board_service.get_board(board_id) if board_id else None
        recent_events = overview["recent_events"]
        if query:
            lowered = query.lower().strip()
            recent_events = [
                row
                for row in recent_events
                if lowered in (row.get("headline") or "").lower()
                or lowered in (row.get("event_type") or "").lower()
            ]
        citations: list[dict[str, Any]] = []
        event_lines = []
        for row in recent_events[:5]:
            event_lines.append(f"- {row['headline']} ({row['event_type']})")
        if board:
            title = f"Weekly Thematic Brief: {board['board']['name']}"
            summary = board["board"].get("description") or "Board-based weekly thematic brief."
        else:
            title = "Weekly Thematic Brief"
            summary = "Recent semiconductor event flow and ranked impact candidates."
        markdown = "\n".join(
            [
                f"# {title}",
                "",
                summary,
                "",
                "## Recent events",
                *event_lines,
                "",
                "## Non-obvious impacts",
                *[
                    f"- {row['ticker']} from {row['headline']} ({row['predicted_lag_bucket']})"
                    for row in overview["top_non_obvious_impacts"][:5]
                ],
            ]
        )
        return {
            "title": title,
            "summary": summary,
            "scope_type": "board" if board_id else "dashboard",
            "scope_id": board_id or "dashboard",
            "citations": citations,
            "sections": {
                "overview": overview,
                "board": board,
            },
            "markdown": markdown,
        }

    def _entity_comparison_brief(self, entity_id: str, compare_entity_id: str) -> dict[str, Any]:
        left = self.entity_service.get_entity_workspace(entity_id)
        right = self.entity_service.get_entity_workspace(compare_entity_id)
        left_entity = left["entity"]
        right_entity = right["entity"]
        summary = (
            f"{left_entity['label']} versus {right_entity['label']} on role, exposure intensity, and linked event flow."
        )
        markdown = "\n".join(
            [
                f"# Entity Comparison Brief: {left_entity['label']} vs {right_entity['label']}",
                "",
                summary,
                "",
                "## Exposure summary",
                f"- {left_entity['label']}: {left['exposure_summary']['event_count']} linked events, avg rank {left['exposure_summary']['avg_rank_score']}",
                f"- {right_entity['label']}: {right['exposure_summary']['event_count']} linked events, avg rank {right['exposure_summary']['avg_rank_score']}",
                "",
                "## Recent linked events",
                *[
                    f"- {row['event_id']}: {row.get('headline') or row['event_id']}"
                    for row in (left["recent_events"][:3] + right["recent_events"][:3])
                ],
            ]
        )
        return {
            "title": f"Entity Comparison Brief: {left_entity['label']} vs {right_entity['label']}",
            "summary": summary,
            "scope_type": "entity_comparison",
            "scope_id": f"{entity_id}|{compare_entity_id}",
            "citations": left["evidence"]["linked_events"][:2] + right["evidence"]["linked_events"][:2],
            "sections": {
                "left": left,
                "right": right,
            },
            "markdown": markdown,
        }

    def _scenario_memo(self, scenario_id: str) -> dict[str, Any]:
        workspace = self.scenario_service.get_scenario_workspace(scenario_id)
        scenario = workspace["scenario"]
        latest_run = workspace["latest_run"] or self.scenario_service.run_scenario(scenario_id)
        impacted_entities = latest_run.get("impacted_entities_json") or []
        contradiction_lines = [
            f"- {row['headline']} ({row['direction']})"
            for row in workspace["contradiction_signals"][:4]
        ] or ["- No contradictory evidence observed yet."]
        watch_lines = [
            f"- {row['item_label']}: {row.get('reason')}"
            for row in workspace["support_signals"][:4]
        ] or ["- No supportive monitor signals observed yet."]
        markdown = "\n".join(
            [
                f"# Scenario Memo: {scenario['name']}",
                "",
                scenario.get("summary") or scenario.get("description") or "Explicit assumption-driven scenario memo.",
                "",
                "## Assumptions",
                *[
                    f"- {row['label']}: {row['expected_direction']} ({row['magnitude']}, confidence {float(row['confidence']):.2f})"
                    for row in workspace["assumptions"]
                ],
                "",
                "## Affected entities and pathways",
                *[
                    f"- {row['ticker']}: {row['direction']} | score {row['total_score']:.2f} | hop {row['best_hop_count']}"
                    for row in impacted_entities[:5]
                ],
                "",
                "## Contradictory evidence / uncertainty",
                *contradiction_lines,
                "",
                "## What to watch next",
                *watch_lines,
            ]
        )
        return {
            "title": f"Scenario Memo: {scenario['name']}",
            "summary": latest_run.get("run_summary") or scenario.get("summary") or "Scenario memo",
            "scope_type": "scenario",
            "scope_id": scenario_id,
            "citations": [],
            "sections": {
                "scenario": scenario,
                "latest_run": latest_run,
                "workspace": workspace,
            },
            "markdown": markdown,
        }

    def _thesis_change_report(self, thesis_id: str) -> dict[str, Any]:
        workspace = self.thesis_service.get_thesis_workspace(thesis_id)
        thesis = workspace["thesis"]
        updates = workspace["updates"]
        support_lines = [
            f"- {row['headline']} ({row['direction']})"
            for row in workspace["support_signals"][:5]
        ] or ["- No supportive evidence observed yet."]
        contradiction_lines = [
            f"- {row['headline']} ({row['direction']})"
            for row in workspace["contradiction_signals"][:5]
        ] or ["- No contradictory evidence observed yet."]
        update_lines = [
            f"- {row['created_at_utc']}: {row['summary']}"
            for row in updates[:5]
        ] or ["- No explicit thesis updates logged yet."]
        markdown = "\n".join(
            [
                f"# Thesis Change Report: {thesis['title']}",
                "",
                thesis["statement"],
                "",
                f"- Current stance: {thesis.get('stance')}",
                f"- Current confidence: {float(thesis.get('confidence') or 0.0):.2f}",
                "",
                "## Supportive evidence",
                *support_lines,
                "",
                "## Contradictory evidence",
                *contradiction_lines,
                "",
                "## Update history",
                *update_lines,
            ]
        )
        return {
            "title": f"Thesis Change Report: {thesis['title']}",
            "summary": updates[0]["summary"] if updates else thesis["statement"],
            "scope_type": "thesis",
            "scope_id": thesis_id,
            "citations": [],
            "sections": {
                "thesis": thesis,
                "workspace": workspace,
            },
            "markdown": markdown,
        }

    def _export_markdown(self, report: dict[str, Any]) -> None:
        reports_dir = self.settings.outputs_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        target_path = reports_dir / f"{report['report_id'].replace(':', '_')}.md"
        target_path.write_text(str(report["markdown"]), encoding="utf-8")
