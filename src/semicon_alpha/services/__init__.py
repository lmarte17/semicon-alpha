from __future__ import annotations

from importlib import import_module


_EXPORTS = {
    "AlertService": "semicon_alpha.services.alerts",
    "BoardService": "semicon_alpha.services.boards",
    "CopilotService": "semicon_alpha.services.copilot",
    "DashboardService": "semicon_alpha.services.dashboard",
    "EntityWorkspaceService": "semicon_alpha.services.entities",
    "EventWorkspaceService": "semicon_alpha.services.events",
    "EvidenceService": "semicon_alpha.services.evidence",
    "GraphExplorerService": "semicon_alpha.services.graph_view",
    "NotesService": "semicon_alpha.services.notes",
    "ReportService": "semicon_alpha.services.reports",
    "ResearchService": "semicon_alpha.services.research",
    "ScenarioService": "semicon_alpha.services.scenarios",
    "SavedQueryService": "semicon_alpha.services.queries",
    "SearchService": "semicon_alpha.services.search",
    "ThesisService": "semicon_alpha.services.theses",
    "WatchlistService": "semicon_alpha.services.watchlists",
    "WorldModelRepository": "semicon_alpha.services.repository",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(name)
    module = import_module(module_name)
    return getattr(module, name)
