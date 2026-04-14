from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from semicon_alpha.appstate import AppStateRepository
from semicon_alpha.api.dependencies import APIServices
from semicon_alpha.api.routes import (
    alerts_router,
    boards_router,
    copilot_router,
    dashboard_router,
    entities_router,
    events_router,
    graph_router,
    notes_router,
    queries_router,
    reports_router,
    scenarios_router,
    search_router,
    theses_router,
    watchlists_router,
)
from semicon_alpha.services import (
    AlertService,
    BoardService,
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
    WatchlistService,
    WorldModelRepository,
)
from semicon_alpha.services.repository import discover_ui_root
from semicon_alpha.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.ensure_directories()

    repo = WorldModelRepository(settings)
    appstate = AppStateRepository(settings)
    evidence_service = EvidenceService(repo)
    graph_service = GraphExplorerService(settings, repo)
    search_service = SearchService(repo)
    dashboard_service = DashboardService(repo)
    event_service = EventWorkspaceService(repo, evidence_service)
    entity_service = EntityWorkspaceService(repo, graph_service, evidence_service)
    watchlist_service = WatchlistService(repo, appstate)
    board_service = BoardService(repo, appstate)
    notes_service = NotesService(appstate)
    query_service = SavedQueryService(appstate, search_service)
    research_service = ResearchService(repo, event_service)
    scenario_service = ScenarioService(settings=settings, repo=repo, appstate=appstate)
    thesis_service = ThesisService(repo=repo, appstate=appstate, scenario_service=scenario_service)
    alert_service = AlertService(
        repo,
        appstate,
        evidence_service,
        scenario_service=scenario_service,
        thesis_service=thesis_service,
    )
    report_service = ReportService(
        settings=settings,
        appstate=appstate,
        dashboard_service=dashboard_service,
        event_service=event_service,
        entity_service=entity_service,
        board_service=board_service,
        research_service=research_service,
        scenario_service=scenario_service,
        thesis_service=thesis_service,
    )
    copilot_service = CopilotService(
        dashboard_service=dashboard_service,
        entity_service=entity_service,
        event_service=event_service,
        graph_service=graph_service,
        search_service=search_service,
        scenario_service=scenario_service,
        thesis_service=thesis_service,
    )

    app = FastAPI(
        title="Semicon Alpha Terminal",
        version="0.6.0-wave5",
        description="Wave 5 terminal with analyst workflows, scenarios, ontology expansion, graph history, and hybrid retrieval.",
    )
    app.state.settings = settings
    app.state.services = APIServices(
        repo=repo,
        dashboard=dashboard_service,
        events=event_service,
        entities=entity_service,
        evidence=evidence_service,
        graph=graph_service,
        search=search_service,
        copilot=copilot_service,
        watchlists=watchlist_service,
        boards=board_service,
        notes=notes_service,
        alerts=alert_service,
        queries=query_service,
        research=research_service,
        reports=report_service,
        scenarios=scenario_service,
        theses=thesis_service,
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "events": int(len(repo.events)),
            "entities": int(len(repo.graph_nodes)),
            "impacts": int(len(repo.event_scores)),
            "ontology_nodes": int(len(repo.ontology_nodes)),
        }

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/terminal")

    ui_root = discover_ui_root(Path(__file__))
    app.mount("/terminal-static", StaticFiles(directory=str(ui_root)), name="terminal-static")

    @app.get("/terminal")
    def terminal_index() -> FileResponse:
        return FileResponse(ui_root / "index.html")

    app.include_router(dashboard_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    app.include_router(entities_router, prefix="/api")
    app.include_router(graph_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(copilot_router, prefix="/api")
    app.include_router(watchlists_router, prefix="/api")
    app.include_router(boards_router, prefix="/api")
    app.include_router(notes_router, prefix="/api")
    app.include_router(alerts_router, prefix="/api")
    app.include_router(queries_router, prefix="/api")
    app.include_router(reports_router, prefix="/api")
    app.include_router(scenarios_router, prefix="/api")
    app.include_router(theses_router, prefix="/api")
    return app


app = create_app()
