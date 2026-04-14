from __future__ import annotations

from typing import Any

from semicon_alpha.appstate import AppStateRepository
from semicon_alpha.services.evidence import EvidenceService
from semicon_alpha.services.helpers import entity_id_to_ticker, has_columns
from semicon_alpha.services.operational_support import matched_event_rows, resolve_item_label
from semicon_alpha.services.repository import WorldModelRepository
from semicon_alpha.services.scenarios import ScenarioService
from semicon_alpha.services.theses import ThesisService


class AlertService:
    def __init__(
        self,
        repo: WorldModelRepository,
        appstate: AppStateRepository,
        evidence_service: EvidenceService,
        scenario_service: ScenarioService | None = None,
        thesis_service: ThesisService | None = None,
    ) -> None:
        self.repo = repo
        self.appstate = appstate
        self.evidence_service = evidence_service
        self.scenario_service = scenario_service
        self.thesis_service = thesis_service

    def list_alerts(self, limit: int = 50, status: str = "active", refresh: bool = True) -> list[dict[str, Any]]:
        if refresh:
            self.refresh_alerts()
        return self.appstate.list_alerts(status=status, limit=limit)

    def dismiss_alert(self, alert_id: str) -> dict[str, Any] | None:
        return self.appstate.dismiss_alert(alert_id)

    def refresh_alerts(self) -> dict[str, Any]:
        generated_count = 0
        watchlists = self.appstate.list_watchlists()
        for watchlist in watchlists:
            items = self.appstate.list_watchlist_items(watchlist["watchlist_id"])
            for item in items:
                generated_count += self._generate_watch_item_alerts(watchlist, item)
        for note in self.appstate.list_notes():
            generated_count += self._generate_contradiction_alerts(note)
        if self.scenario_service is not None:
            for scenario in self.scenario_service.list_scenarios():
                generated_count += self._generate_scenario_alerts(str(scenario["scenario_id"]))
        if self.thesis_service is not None:
            for thesis in self.thesis_service.list_theses():
                generated_count += self._generate_thesis_alerts(str(thesis["thesis_id"]))
        return {"generated_count": generated_count}

    def _generate_watch_item_alerts(self, watchlist: dict[str, Any], item: dict[str, Any]) -> int:
        generated = 0
        item_type = str(item["item_type"])
        item_id = str(item["item_id_value"])
        item_label = item.get("label") or resolve_item_label(self.repo, item_type, item_id)
        for event_row in matched_event_rows(self.repo, item_type, item_id, limit=8):
            event_id = str(event_row["event_id"])
            evidence = self.evidence_service.get_event_evidence(event_id)
            severity = _severity_from_event(event_row)
            body = (
                f"'{event_row.get('headline')}' matched watched {item_type} '{item_label}'. "
                f"Direction is {event_row.get('direction')} with severity {event_row.get('severity')}."
            )
            self.appstate.upsert_alert(
                fingerprint=f"watch:{item['item_id']}:{event_id}",
                alert_type="watch_event",
                severity=severity,
                title=f"New event for watched {item_type}",
                body=body,
                entity_ids=_entity_ids_for_alert(item_type, item_id, event_id),
                event_ids=[event_id],
                theme_ids=[item_id] if item_type == "theme" else [],
                evidence=evidence.get("source_documents", []),
                suggested_action="Open the event workspace and inspect ranked impacts and evidence.",
            )
            generated += 1

        if item_type == "entity":
            generated += self._generate_score_signal_alerts(item, item_label)
        return generated

    def _generate_score_signal_alerts(self, item: dict[str, Any], item_label: str) -> int:
        if not has_columns(self.repo.event_scores, "ticker", "event_id", "total_rank_score"):
            return 0
        ticker = entity_id_to_ticker(str(item["item_id_value"]))
        if not ticker:
            return 0
        scores = self.repo.event_scores.copy()
        if "published_at_utc" in scores.columns:
            scores = scores.sort_values("published_at_utc", ascending=True)
        scores = scores.loc[scores["ticker"] == ticker]
        if scores.empty:
            return 0

        generated = 0
        prior_scores: list[float] = []
        for row in scores.to_dict(orient="records"):
            current_score = float(row.get("total_rank_score") or 0.0)
            prior_avg = sum(prior_scores) / len(prior_scores) if prior_scores else None
            if (prior_avg is not None and current_score >= prior_avg + 0.15) or (
                prior_avg is None and current_score >= 0.85
            ):
                event_id = str(row["event_id"])
                event_row = self.repo.events.loc[self.repo.events["event_id"] == event_id]
                headline = None if event_row.empty else str(event_row.iloc[0]["headline"])
                self.appstate.upsert_alert(
                    fingerprint=f"score-signal:{item['item_id']}:{event_id}",
                    alert_type="score_signal",
                    severity="high" if current_score >= 0.9 else "medium",
                    title=f"Score signal for watched entity {item_label}",
                    body=(
                        f"{item_label} reached rank score {current_score:.2f}"
                        + (f" versus historical average {prior_avg:.2f}." if prior_avg is not None else ".")
                        + (f" Event: {headline}." if headline else "")
                    ),
                    entity_ids=[str(item["item_id_value"])],
                    event_ids=[event_id],
                    evidence=self.evidence_service.get_event_evidence(event_id).get("source_documents", []),
                    suggested_action="Check the event workspace and compare the path rationale against prior linked events.",
                )
                generated += 1
            prior_scores.append(current_score)
        return generated

    def _generate_contradiction_alerts(self, note: dict[str, Any]) -> int:
        stance = (note.get("stance") or "").lower()
        if stance not in {"positive", "negative"}:
            return 0
        subject_type = str(note["subject_type"])
        subject_id = str(note["subject_id"])
        generated = 0
        desired_opposite = "negative" if stance == "positive" else "positive"

        if subject_type == "entity" and has_columns(self.repo.event_scores, "entity_id", "impact_direction"):
            match = self.repo.event_scores.loc[self.repo.event_scores["entity_id"] == subject_id].sort_values(
                "published_at_utc", ascending=False
            )
            for row in match.head(6).to_dict(orient="records"):
                if row.get("impact_direction") != desired_opposite:
                    continue
                event_id = str(row["event_id"])
                event_row = self.repo.events.loc[self.repo.events["event_id"] == event_id]
                headline = None if event_row.empty else str(event_row.iloc[0]["headline"])
                self.appstate.upsert_alert(
                    fingerprint=f"contradiction:{note['note_id']}:{event_id}",
                    alert_type="contradiction",
                    severity="high",
                    title="Note contradiction detected",
                    body=(
                        f"An entity note with {stance} stance conflicts with a new {desired_opposite} impact. "
                        + (f"Event: {headline}." if headline else "")
                    ),
                    entity_ids=[subject_id],
                    event_ids=[event_id],
                    evidence=self.evidence_service.get_event_evidence(event_id).get("source_documents", []),
                    suggested_action="Review the note against the new event and update the interpretation if needed.",
                )
                generated += 1

        if subject_type == "theme" and has_columns(self.repo.event_themes, "theme_id", "event_id"):
            event_rows = matched_event_rows(self.repo, "theme", subject_id, limit=6)
            for event_row in event_rows:
                if event_row.get("direction") != desired_opposite:
                    continue
                event_id = str(event_row["event_id"])
                self.appstate.upsert_alert(
                    fingerprint=f"contradiction:{note['note_id']}:{event_id}",
                    alert_type="contradiction",
                    severity="medium",
                    title="Theme note contradiction detected",
                    body=(
                        f"A theme note with {stance} stance conflicts with an event moving {desired_opposite}. "
                        f"Event: {event_row.get('headline')}."
                    ),
                    event_ids=[event_id],
                    theme_ids=[subject_id],
                    evidence=self.evidence_service.get_event_evidence(event_id).get("source_documents", []),
                    suggested_action="Inspect the theme evidence and decide whether the note still holds.",
                )
                generated += 1

        return generated

    def _generate_scenario_alerts(self, scenario_id: str) -> int:
        if self.scenario_service is None:
            return 0
        generated = 0
        for signal in self.scenario_service.get_monitor_signals(scenario_id, limit=10):
            event_id = _coerce_optional_str(signal.get("event_id"))
            evidence = []
            if event_id:
                try:
                    evidence = self.evidence_service.get_event_evidence(event_id).get("source_documents", [])
                except KeyError:
                    evidence = []
            alert_type = "scenario_support" if signal["signal_state"] == "support" else "scenario_invalidation"
            self.appstate.upsert_alert(
                fingerprint=f"scenario:{scenario_id}:{signal['item_type']}:{signal['item_id']}:{event_id}:{signal['signal_state']}",
                alert_type=alert_type,
                severity="medium" if signal["signal_state"] == "support" else "high",
                title="Scenario assumption supported"
                if signal["signal_state"] == "support"
                else "Scenario assumption weakened",
                body=(
                    f"{signal['item_label']} saw {signal.get('direction')} evidence via '{signal.get('headline')}'."
                ),
                entity_ids=[signal["item_id"]] if signal["item_type"] == "entity" else [],
                event_ids=[event_id] if event_id else [],
                theme_ids=[signal["item_id"]] if signal["item_type"] == "theme" else [],
                scenario_ids=[scenario_id],
                evidence=evidence,
                suggested_action="Open the scenario workspace and inspect whether the monitored path still holds.",
            )
            generated += 1
        return generated

    def _generate_thesis_alerts(self, thesis_id: str) -> int:
        if self.thesis_service is None:
            return 0
        generated = 0
        for signal in self.thesis_service.get_monitor_signals(thesis_id, limit=10):
            event_id = _coerce_optional_str(signal.get("event_id"))
            evidence = []
            if event_id:
                try:
                    evidence = self.evidence_service.get_event_evidence(event_id).get("source_documents", [])
                except KeyError:
                    evidence = []
            alert_type = "thesis_support" if signal["signal_state"] == "support" else "thesis_contradiction"
            self.appstate.upsert_alert(
                fingerprint=f"thesis:{thesis_id}:{signal['thesis_link_type']}:{signal['thesis_link_id']}:{event_id}:{signal['signal_state']}",
                alert_type=alert_type,
                severity="medium" if signal["signal_state"] == "support" else "high",
                title="Thesis evidence supported"
                if signal["signal_state"] == "support"
                else "Thesis contradiction detected",
                body=(
                    f"{signal['item_label']} produced {signal.get('direction')} evidence via '{signal.get('headline')}'."
                ),
                entity_ids=[signal["item_id"]] if signal["item_type"] == "entity" else [],
                event_ids=[event_id] if event_id else [],
                theme_ids=[signal["item_id"]] if signal["item_type"] == "theme" else [],
                thesis_ids=[thesis_id],
                scenario_ids=[signal["thesis_link_id"]] if signal.get("thesis_link_type") == "scenario" else [],
                evidence=evidence,
                suggested_action="Open the thesis workspace and decide whether confidence should change.",
            )
            generated += 1
        return generated


def _severity_from_event(event_row: dict[str, Any]) -> str:
    severity = str(event_row.get("severity") or "medium").lower()
    market_relevance = float(event_row.get("market_relevance_score") or 0.0)
    if severity == "high" or market_relevance >= 0.8:
        return "high"
    if severity == "low":
        return "low"
    return "medium"


def _entity_ids_for_alert(item_type: str, item_id: str, event_id: str) -> list[str]:
    if item_type == "entity":
        return [item_id]
    return []


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
