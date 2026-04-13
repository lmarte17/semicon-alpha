from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from semicon_alpha.api.dependencies import APIServices
from semicon_alpha.api.routes import (
    copilot_router,
    dashboard_router,
    entities_router,
    events_router,
    graph_router,
    search_router,
)
from semicon_alpha.services import (
    CopilotService,
    DashboardService,
    EntityWorkspaceService,
    EventWorkspaceService,
    EvidenceService,
    GraphExplorerService,
    SearchService,
    WorldModelRepository,
)
from semicon_alpha.services.repository import discover_ui_root
from semicon_alpha.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.ensure_directories()

    repo = WorldModelRepository(settings)
    evidence_service = EvidenceService(repo)
    graph_service = GraphExplorerService(settings, repo)
    search_service = SearchService(repo)
    dashboard_service = DashboardService(repo)
    event_service = EventWorkspaceService(repo, evidence_service)
    entity_service = EntityWorkspaceService(repo, graph_service, evidence_service)
    copilot_service = CopilotService(
        dashboard_service=dashboard_service,
        entity_service=entity_service,
        event_service=event_service,
        graph_service=graph_service,
        search_service=search_service,
    )

    app = FastAPI(
        title="Semicon Alpha Terminal",
        version="0.2.0-wave1",
        description="Wave 1 analyst workflow MVP over the semiconductor intelligence engine.",
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
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "events": int(len(repo.events)),
            "entities": int(len(repo.graph_nodes)),
            "impacts": int(len(repo.event_scores)),
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
    return app


app = create_app()
