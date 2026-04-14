from __future__ import annotations

from typing import Any

from semicon_alpha.appstate import AppStateRepository
from semicon_alpha.services.operational_support import resolve_item_label
from semicon_alpha.services.repository import WorldModelRepository
from semicon_alpha.services.scenarios import ScenarioService


class ThesisService:
    def __init__(
        self,
        repo: WorldModelRepository,
        appstate: AppStateRepository,
        scenario_service: ScenarioService,
    ) -> None:
        self.repo = repo
        self.appstate = appstate
        self.scenario_service = scenario_service

    def list_theses(self) -> list[dict[str, Any]]:
        return self.appstate.list_theses()

    def create_thesis(
        self,
        title: str,
        statement: str,
        stance: str = "mixed",
        confidence: float = 0.5,
        status: str = "active",
        time_horizon: str | None = None,
        links: list[dict[str, Any]] | None = None,
        initial_update: str | None = None,
    ) -> dict[str, Any]:
        thesis = self.appstate.create_thesis(
            title=title,
            statement=statement,
            stance=stance,
            confidence=confidence,
            status=status,
            time_horizon=time_horizon,
        )
        thesis_id = str(thesis["thesis_id"])
        for link in links or []:
            self.appstate.add_thesis_link(
                thesis_id=thesis_id,
                item_type=str(link["item_type"]),
                item_id_value=str(link["item_id"]),
                relationship=str(link.get("relationship") or "supports"),
                label=link.get("label") or self._resolve_label(str(link["item_type"]), str(link["item_id"])),
                metadata=link.get("metadata"),
            )
        if initial_update:
            self.appstate.add_thesis_update(thesis_id=thesis_id, summary=initial_update, confidence=confidence)
        return self.get_thesis_workspace(thesis_id)

    def add_update(
        self,
        thesis_id: str,
        summary: str,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        if self.appstate.get_thesis(thesis_id) is None:
            raise KeyError(f"Unknown thesis_id: {thesis_id}")
        return self.appstate.add_thesis_update(thesis_id=thesis_id, summary=summary, confidence=confidence)

    def get_thesis_workspace(
        self,
        thesis_id: str,
        alerts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        thesis = self.appstate.get_thesis(thesis_id)
        if thesis is None:
            raise KeyError(f"Unknown thesis_id: {thesis_id}")
        links = self.appstate.list_thesis_links(thesis_id)
        updates = self.appstate.list_thesis_updates(thesis_id)
        signals = self.get_monitor_signals(thesis_id, limit=16)
        related_alerts = [
            alert
            for alert in (alerts or [])
            if thesis_id in (alert.get("thesis_ids_json") or [])
        ]
        return {
            "thesis": thesis,
            "links": links,
            "updates": updates,
            "support_signals": [signal for signal in signals if signal["signal_state"] == "support"],
            "contradiction_signals": [signal for signal in signals if signal["signal_state"] == "contradiction"],
            "alerts": related_alerts[:16],
        }

    def get_monitor_signals(self, thesis_id: str, limit: int = 12) -> list[dict[str, Any]]:
        thesis = self.appstate.get_thesis(thesis_id)
        if thesis is None:
            raise KeyError(f"Unknown thesis_id: {thesis_id}")
        stance = str(thesis.get("stance") or "mixed")
        links = self.appstate.list_thesis_links(thesis_id)
        signals: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for link in links:
            item_type = str(link["item_type"])
            item_id = str(link["item_id_value"])
            relationship = str(link.get("relationship") or "supports")
            expected_direction = _expected_direction_for_link(stance, relationship)

            if item_type == "scenario":
                source_signals = self.scenario_service.get_monitor_signals(item_id, limit=max(4, limit))
                for signal in source_signals:
                    signal_state = signal["signal_state"]
                    if relationship == "contradicts":
                        signal_state = "support" if signal_state == "contradiction" else "contradiction"
                    fingerprint = (item_type, item_id, signal.get("event_id") or signal.get("headline") or "")
                    if fingerprint in seen:
                        continue
                    seen.add(fingerprint)
                    signals.append(
                        {
                            **signal,
                            "signal_state": signal_state,
                            "thesis_id": thesis_id,
                            "thesis_link_type": item_type,
                            "thesis_link_id": item_id,
                            "reason": "Scenario monitor evidence aligned with the linked thesis."
                            if signal_state == "support"
                            else "Scenario monitor evidence contradicted the linked thesis.",
                        }
                    )
                continue

            for signal in self.scenario_service.collect_item_signals(
                item_type=item_type,
                item_id=item_id,
                expected_direction=expected_direction,
                limit=max(4, limit),
            ):
                fingerprint = (item_type, item_id, signal.get("event_id") or signal.get("headline") or "")
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                signals.append(
                    {
                        **signal,
                        "thesis_id": thesis_id,
                        "thesis_link_type": item_type,
                        "thesis_link_id": item_id,
                    }
                )
        signals.sort(key=lambda row: (row.get("published_at_utc") or "", row.get("score_hint") or 0.0), reverse=True)
        return signals[:limit]

    def _resolve_label(self, item_type: str, item_id: str) -> str:
        if item_type == "scenario":
            scenario = self.appstate.get_scenario(item_id)
            if scenario is not None:
                return str(scenario["name"])
        if item_type in {"entity", "theme", "segment", "event_type"}:
            return resolve_item_label(self.repo, item_type, item_id)
        if item_type == "event":
            match = self.repo.events.loc[self.repo.events["event_id"] == item_id]
            if not match.empty:
                return str(match.iloc[0]["headline"])
        return item_id


def _expected_direction_for_link(stance: str, relationship: str) -> str | None:
    if stance not in {"positive", "negative"}:
        return None
    if relationship == "contradicts":
        return "negative" if stance == "positive" else "positive"
    return stance
