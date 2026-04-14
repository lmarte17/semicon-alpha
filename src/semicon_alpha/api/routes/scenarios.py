from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from semicon_alpha.api.dependencies import APIServices, get_services
from semicon_alpha.api.schemas import CreateScenarioRequest, ScenarioWorkspace


router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("")
def list_scenarios(services: APIServices = Depends(get_services)) -> list[dict]:
    return services.scenarios.list_scenarios()


@router.post("", response_model=ScenarioWorkspace)
def create_scenario(
    request: CreateScenarioRequest,
    services: APIServices = Depends(get_services),
) -> ScenarioWorkspace:
    payload = services.scenarios.create_scenario(
        name=request.name,
        description=request.description,
        summary=request.summary,
        status=request.status,
        assumptions=[
            {
                "item_type": row.item_type,
                "item_id": row.item_id,
                "direction": row.direction,
                "magnitude": row.magnitude,
                "confidence": row.confidence,
                "rationale": row.rationale,
                "label": row.label,
            }
            for row in request.assumptions
        ],
        monitors=None
        if request.monitors is None
        else [
            {
                "item_type": row.item_type,
                "item_id": row.item_id,
                "expected_direction": row.expected_direction,
                "label": row.label,
                "threshold": row.threshold,
            }
            for row in request.monitors
        ],
    )
    return ScenarioWorkspace(**payload)


@router.get("/{scenario_id}", response_model=ScenarioWorkspace)
def get_scenario(
    scenario_id: str,
    services: APIServices = Depends(get_services),
) -> ScenarioWorkspace:
    try:
        payload = services.scenarios.get_scenario_workspace(
            scenario_id,
            alerts=services.alerts.list_alerts(refresh=True),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ScenarioWorkspace(**payload)


@router.post("/{scenario_id}/run")
def run_scenario(
    scenario_id: str,
    services: APIServices = Depends(get_services),
) -> dict:
    try:
        return services.scenarios.run_scenario(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
