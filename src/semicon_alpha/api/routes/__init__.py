from semicon_alpha.api.routes.alerts import router as alerts_router
from semicon_alpha.api.routes.boards import router as boards_router
from semicon_alpha.api.routes.copilot import router as copilot_router
from semicon_alpha.api.routes.dashboard import router as dashboard_router
from semicon_alpha.api.routes.entities import router as entities_router
from semicon_alpha.api.routes.events import router as events_router
from semicon_alpha.api.routes.graph import router as graph_router
from semicon_alpha.api.routes.notes import router as notes_router
from semicon_alpha.api.routes.queries import router as queries_router
from semicon_alpha.api.routes.reports import router as reports_router
from semicon_alpha.api.routes.scenarios import router as scenarios_router
from semicon_alpha.api.routes.search import router as search_router
from semicon_alpha.api.routes.theses import router as theses_router
from semicon_alpha.api.routes.watchlists import router as watchlists_router

__all__ = [
    "alerts_router",
    "boards_router",
    "copilot_router",
    "dashboard_router",
    "entities_router",
    "events_router",
    "graph_router",
    "notes_router",
    "queries_router",
    "reports_router",
    "scenarios_router",
    "search_router",
    "theses_router",
    "watchlists_router",
]
