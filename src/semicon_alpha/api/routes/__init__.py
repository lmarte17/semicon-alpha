from semicon_alpha.api.routes.copilot import router as copilot_router
from semicon_alpha.api.routes.dashboard import router as dashboard_router
from semicon_alpha.api.routes.entities import router as entities_router
from semicon_alpha.api.routes.events import router as events_router
from semicon_alpha.api.routes.graph import router as graph_router
from semicon_alpha.api.routes.search import router as search_router

__all__ = [
    "copilot_router",
    "dashboard_router",
    "entities_router",
    "events_router",
    "graph_router",
    "search_router",
]
