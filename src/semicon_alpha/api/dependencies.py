from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from semicon_alpha.services import (
    CopilotService,
    DashboardService,
    EntityWorkspaceService,
    EventWorkspaceService,
    EvidenceService,
    GraphExplorerService,
    NotesService,
    ReportService,
    ResearchService,
    ScenarioService,
    SavedQueryService,
    SearchService,
    ThesisService,
    AlertService,
    BoardService,
    WatchlistService,
    WorldModelRepository,
)


@dataclass
class APIServices:
    repo: WorldModelRepository
    dashboard: DashboardService
    events: EventWorkspaceService
    entities: EntityWorkspaceService
    evidence: EvidenceService
    graph: GraphExplorerService
    search: SearchService
    copilot: CopilotService
    watchlists: WatchlistService
    boards: BoardService
    notes: NotesService
    alerts: AlertService
    queries: SavedQueryService
    research: ResearchService
    reports: ReportService
    scenarios: ScenarioService
    theses: ThesisService


def get_services(request: Request) -> APIServices:
    return request.app.state.services
