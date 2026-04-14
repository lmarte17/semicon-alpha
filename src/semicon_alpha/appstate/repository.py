from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

from semicon_alpha.settings import Settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class AppStateRepository:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.appstate_path
        self._ensure_parent()
        self.init_schema()

    def _ensure_parent(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS watchlists (
                    watchlist_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS watchlist_items (
                    item_id TEXT PRIMARY KEY,
                    watchlist_id TEXT NOT NULL REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
                    item_type TEXT NOT NULL,
                    item_id_value TEXT NOT NULL,
                    label TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(watchlist_id, item_type, item_id_value)
                );

                CREATE TABLE IF NOT EXISTS boards (
                    board_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    layout_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS board_items (
                    board_item_id TEXT PRIMARY KEY,
                    board_id TEXT NOT NULL REFERENCES boards(board_id) ON DELETE CASCADE,
                    item_type TEXT NOT NULL,
                    item_id_value TEXT,
                    title TEXT,
                    content TEXT,
                    position_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notes (
                    note_id TEXT PRIMARY KEY,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    board_id TEXT REFERENCES boards(board_id) ON DELETE SET NULL,
                    title TEXT,
                    body TEXT NOT NULL,
                    stance TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS saved_queries (
                    query_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    query_type TEXT NOT NULL DEFAULT 'global_search',
                    filters_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    entity_ids_json TEXT NOT NULL DEFAULT '[]',
                    event_ids_json TEXT NOT NULL DEFAULT '[]',
                    theme_ids_json TEXT NOT NULL DEFAULT '[]',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    suggested_action TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    report_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT,
                    scope_type TEXT,
                    scope_id TEXT,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    markdown TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scenarios (
                    scenario_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    summary TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scenario_assumptions (
                    assumption_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
                    item_type TEXT NOT NULL,
                    item_id_value TEXT NOT NULL,
                    label TEXT,
                    expected_direction TEXT NOT NULL,
                    magnitude TEXT NOT NULL DEFAULT 'medium',
                    confidence REAL NOT NULL DEFAULT 0.7,
                    rationale TEXT,
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(scenario_id, item_type, item_id_value, expected_direction)
                );

                CREATE TABLE IF NOT EXISTS scenario_monitors (
                    monitor_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
                    item_type TEXT NOT NULL,
                    item_id_value TEXT NOT NULL,
                    label TEXT,
                    expected_direction TEXT,
                    threshold_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(scenario_id, item_type, item_id_value, expected_direction)
                );

                CREATE TABLE IF NOT EXISTS scenario_runs (
                    run_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
                    run_summary TEXT,
                    assumptions_json TEXT NOT NULL DEFAULT '[]',
                    impacted_entities_json TEXT NOT NULL DEFAULT '[]',
                    affected_paths_json TEXT NOT NULL DEFAULT '[]',
                    support_signals_json TEXT NOT NULL DEFAULT '[]',
                    contradiction_signals_json TEXT NOT NULL DEFAULT '[]',
                    created_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS theses (
                    thesis_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    stance TEXT NOT NULL DEFAULT 'mixed',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    status TEXT NOT NULL DEFAULT 'active',
                    time_horizon TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS thesis_links (
                    link_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(thesis_id) ON DELETE CASCADE,
                    item_type TEXT NOT NULL,
                    item_id_value TEXT NOT NULL,
                    relationship TEXT NOT NULL DEFAULT 'supports',
                    label TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(thesis_id, item_type, item_id_value, relationship)
                );

                CREATE TABLE IF NOT EXISTS thesis_updates (
                    update_id TEXT PRIMARY KEY,
                    thesis_id TEXT NOT NULL REFERENCES theses(thesis_id) ON DELETE CASCADE,
                    summary TEXT NOT NULL,
                    confidence REAL,
                    created_at_utc TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id
                ON watchlist_items(watchlist_id);

                CREATE INDEX IF NOT EXISTS idx_board_items_board_id
                ON board_items(board_id);

                CREATE INDEX IF NOT EXISTS idx_notes_subject
                ON notes(subject_type, subject_id);

                CREATE INDEX IF NOT EXISTS idx_alerts_status
                ON alerts(status, updated_at_utc DESC);

                CREATE INDEX IF NOT EXISTS idx_reports_created
                ON reports(created_at_utc DESC);

                CREATE INDEX IF NOT EXISTS idx_scenario_assumptions_scenario
                ON scenario_assumptions(scenario_id, created_at_utc DESC);

                CREATE INDEX IF NOT EXISTS idx_scenario_monitors_scenario
                ON scenario_monitors(scenario_id, created_at_utc DESC);

                CREATE INDEX IF NOT EXISTS idx_scenario_runs_scenario
                ON scenario_runs(scenario_id, created_at_utc DESC);

                CREATE INDEX IF NOT EXISTS idx_thesis_links_thesis
                ON thesis_links(thesis_id, created_at_utc DESC);

                CREATE INDEX IF NOT EXISTS idx_thesis_updates_thesis
                ON thesis_updates(thesis_id, created_at_utc DESC);
                """
            )
            self._ensure_column(connection, "alerts", "scenario_ids_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(connection, "alerts", "thesis_ids_json", "TEXT NOT NULL DEFAULT '[]'")

    def list_watchlists(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    watchlists.*,
                    COUNT(watchlist_items.item_id) AS item_count
                FROM watchlists
                LEFT JOIN watchlist_items ON watchlist_items.watchlist_id = watchlists.watchlist_id
                GROUP BY watchlists.watchlist_id
                ORDER BY watchlists.updated_at_utc DESC, watchlists.name ASC
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def create_watchlist(self, name: str, description: str | None = None) -> dict[str, Any]:
        now = utc_now_iso()
        watchlist_id = f"watchlist:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watchlists (
                    watchlist_id, name, description, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (watchlist_id, name.strip(), _clean_text(description), now, now),
            )
        return self.get_watchlist(watchlist_id)

    def get_watchlist(self, watchlist_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM watchlists WHERE watchlist_id = ?",
                (watchlist_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def list_watchlist_items(self, watchlist_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM watchlist_items
                WHERE watchlist_id = ?
                ORDER BY created_at_utc DESC
                """,
                (watchlist_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def add_watchlist_item(
        self,
        watchlist_id: str,
        item_type: str,
        item_id_value: str,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        existing = self._find_watchlist_item(watchlist_id, item_type, item_id_value)
        if existing is not None:
            return existing
        item_id = f"watchitem:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watchlist_items (
                    item_id, watchlist_id, item_type, item_id_value, label, metadata_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    watchlist_id,
                    item_type,
                    item_id_value,
                    _clean_text(label),
                    json.dumps(metadata or {}),
                    now,
                ),
            )
            connection.execute(
                "UPDATE watchlists SET updated_at_utc = ? WHERE watchlist_id = ?",
                (now, watchlist_id),
            )
        return self._find_watchlist_item(watchlist_id, item_type, item_id_value) or {}

    def delete_watchlist_item(self, item_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM watchlist_items WHERE item_id = ?", (item_id,))

    def list_boards(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    boards.*,
                    COUNT(board_items.board_item_id) AS item_count
                FROM boards
                LEFT JOIN board_items ON board_items.board_id = boards.board_id
                GROUP BY boards.board_id
                ORDER BY boards.updated_at_utc DESC, boards.name ASC
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def create_board(
        self,
        name: str,
        description: str | None = None,
        layout: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        board_id = f"board:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO boards (
                    board_id, name, description, layout_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (board_id, name.strip(), _clean_text(description), json.dumps(layout or {}), now, now),
            )
        return self.get_board(board_id)

    def get_board(self, board_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM boards WHERE board_id = ?",
                (board_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def list_board_items(self, board_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM board_items
                WHERE board_id = ?
                ORDER BY created_at_utc DESC
                """,
                (board_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def add_board_item(
        self,
        board_id: str,
        item_type: str,
        item_id_value: str | None = None,
        title: str | None = None,
        content: str | None = None,
        position: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        board_item_id = f"boarditem:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO board_items (
                    board_item_id, board_id, item_type, item_id_value, title, content, position_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    board_item_id,
                    board_id,
                    item_type,
                    item_id_value,
                    _clean_text(title),
                    _clean_text(content),
                    json.dumps(position or {}),
                    now,
                ),
            )
            connection.execute(
                "UPDATE boards SET updated_at_utc = ? WHERE board_id = ?",
                (now, board_id),
            )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM board_items WHERE board_item_id = ?",
                (board_item_id,),
            ).fetchone()
        return {} if row is None else _row_to_dict(row)

    def list_notes(
        self,
        subject_type: str | None = None,
        subject_id: str | None = None,
        board_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if subject_type:
            clauses.append("subject_type = ?")
            params.append(subject_type)
        if subject_id:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        if board_id:
            clauses.append("board_id = ?")
            params.append(board_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM notes
                {where}
                ORDER BY updated_at_utc DESC, created_at_utc DESC
                """,
                params,
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def create_note(
        self,
        subject_type: str,
        subject_id: str,
        body: str,
        title: str | None = None,
        stance: str | None = None,
        board_id: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        note_id = f"note:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO notes (
                    note_id, subject_type, subject_id, board_id, title, body, stance, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    note_id,
                    subject_type,
                    subject_id,
                    board_id,
                    _clean_text(title),
                    body.strip(),
                    _clean_text(stance),
                    now,
                    now,
                ),
            )
        return self.get_note(note_id) or {}

    def get_note(self, note_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM notes WHERE note_id = ?",
                (note_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def list_saved_queries(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM saved_queries
                ORDER BY updated_at_utc DESC, name ASC
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def create_saved_query(
        self,
        name: str,
        query_text: str,
        query_type: str = "global_search",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        query_id = f"query:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO saved_queries (
                    query_id, name, query_text, query_type, filters_json, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (query_id, name.strip(), query_text.strip(), query_type, json.dumps(filters or {}), now, now),
            )
        return self.get_saved_query(query_id) or {}

    def get_saved_query(self, query_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM saved_queries WHERE query_id = ?",
                (query_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def list_alerts(self, status: str | None = "active", limit: int = 100) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM alerts
                {where}
                ORDER BY updated_at_utc DESC, created_at_utc DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def upsert_alert(
        self,
        *,
        fingerprint: str,
        alert_type: str,
        severity: str,
        title: str,
        body: str,
        entity_ids: list[str] | None = None,
        event_ids: list[str] | None = None,
        theme_ids: list[str] | None = None,
        scenario_ids: list[str] | None = None,
        thesis_ids: list[str] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        suggested_action: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        alert_id = f"alert:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO alerts (
                    alert_id, fingerprint, alert_type, severity, title, body,
                    entity_ids_json, event_ids_json, theme_ids_json, scenario_ids_json, thesis_ids_json, evidence_json,
                    suggested_action, status, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    alert_type = excluded.alert_type,
                    severity = excluded.severity,
                    title = excluded.title,
                    body = excluded.body,
                    entity_ids_json = excluded.entity_ids_json,
                    event_ids_json = excluded.event_ids_json,
                    theme_ids_json = excluded.theme_ids_json,
                    scenario_ids_json = excluded.scenario_ids_json,
                    thesis_ids_json = excluded.thesis_ids_json,
                    evidence_json = excluded.evidence_json,
                    suggested_action = excluded.suggested_action,
                    status = excluded.status,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    alert_id,
                    fingerprint,
                    alert_type,
                    severity,
                    title,
                    body,
                    json.dumps(entity_ids or []),
                    json.dumps(event_ids or []),
                    json.dumps(theme_ids or []),
                    json.dumps(scenario_ids or []),
                    json.dumps(thesis_ids or []),
                    json.dumps(evidence or []),
                    _clean_text(suggested_action),
                    status,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM alerts WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        return {} if row is None else _row_to_dict(row)

    def dismiss_alert(self, alert_id: str) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self._connect() as connection:
            connection.execute(
                "UPDATE alerts SET status = 'dismissed', updated_at_utc = ? WHERE alert_id = ?",
                (now, alert_id),
            )
            row = connection.execute(
                "SELECT * FROM alerts WHERE alert_id = ?",
                (alert_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def create_report(
        self,
        report_type: str,
        title: str,
        markdown: str,
        summary: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        citations: list[dict[str, Any]] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        report_id = f"report:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reports (
                    report_id, report_type, title, summary, scope_type, scope_id,
                    citations_json, payload_json, markdown, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    report_type,
                    title.strip(),
                    _clean_text(summary),
                    _clean_text(scope_type),
                    _clean_text(scope_id),
                    json.dumps(citations or []),
                    json.dumps(payload or {}),
                    markdown,
                    now,
                ),
            )
        return self.get_report(report_id) or {}

    def list_reports(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM reports
                ORDER BY created_at_utc DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def list_scenarios(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    scenarios.*,
                    COUNT(DISTINCT scenario_assumptions.assumption_id) AS assumption_count,
                    COUNT(DISTINCT scenario_runs.run_id) AS run_count
                FROM scenarios
                LEFT JOIN scenario_assumptions
                    ON scenario_assumptions.scenario_id = scenarios.scenario_id
                LEFT JOIN scenario_runs
                    ON scenario_runs.scenario_id = scenarios.scenario_id
                GROUP BY scenarios.scenario_id
                ORDER BY scenarios.updated_at_utc DESC, scenarios.name ASC
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def create_scenario(
        self,
        name: str,
        description: str | None = None,
        summary: str | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        now = utc_now_iso()
        scenario_id = f"scenario:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scenarios (
                    scenario_id, name, description, summary, status, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (scenario_id, name.strip(), _clean_text(description), _clean_text(summary), status, now, now),
            )
        return self.get_scenario(scenario_id) or {}

    def get_scenario(self, scenario_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scenarios WHERE scenario_id = ?",
                (scenario_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def list_scenario_assumptions(self, scenario_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scenario_assumptions
                WHERE scenario_id = ?
                ORDER BY created_at_utc ASC, label ASC, item_id_value ASC
                """,
                (scenario_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def add_scenario_assumption(
        self,
        scenario_id: str,
        item_type: str,
        item_id_value: str,
        expected_direction: str,
        label: str | None = None,
        magnitude: str = "medium",
        confidence: float = 0.7,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        existing = self._find_scenario_assumption(scenario_id, item_type, item_id_value, expected_direction)
        if existing is not None:
            return existing
        assumption_id = f"assumption:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scenario_assumptions (
                    assumption_id, scenario_id, item_type, item_id_value, label, expected_direction,
                    magnitude, confidence, rationale, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assumption_id,
                    scenario_id,
                    item_type,
                    item_id_value,
                    _clean_text(label),
                    expected_direction,
                    magnitude,
                    confidence,
                    _clean_text(rationale),
                    now,
                ),
            )
            connection.execute(
                "UPDATE scenarios SET updated_at_utc = ? WHERE scenario_id = ?",
                (now, scenario_id),
            )
            row = connection.execute(
                "SELECT * FROM scenario_assumptions WHERE assumption_id = ?",
                (assumption_id,),
            ).fetchone()
        return {} if row is None else _row_to_dict(row)

    def list_scenario_monitors(self, scenario_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scenario_monitors
                WHERE scenario_id = ?
                ORDER BY created_at_utc ASC, label ASC, item_id_value ASC
                """,
                (scenario_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def add_scenario_monitor(
        self,
        scenario_id: str,
        item_type: str,
        item_id_value: str,
        expected_direction: str | None = None,
        label: str | None = None,
        threshold: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        existing = self._find_scenario_monitor(scenario_id, item_type, item_id_value, expected_direction)
        if existing is not None:
            return existing
        monitor_id = f"monitor:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scenario_monitors (
                    monitor_id, scenario_id, item_type, item_id_value, label, expected_direction,
                    threshold_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    monitor_id,
                    scenario_id,
                    item_type,
                    item_id_value,
                    _clean_text(label),
                    _clean_text(expected_direction),
                    json.dumps(threshold or {}),
                    now,
                ),
            )
            connection.execute(
                "UPDATE scenarios SET updated_at_utc = ? WHERE scenario_id = ?",
                (now, scenario_id),
            )
            row = connection.execute(
                "SELECT * FROM scenario_monitors WHERE monitor_id = ?",
                (monitor_id,),
            ).fetchone()
        return {} if row is None else _row_to_dict(row)

    def create_scenario_run(
        self,
        scenario_id: str,
        run_summary: str | None,
        assumptions: list[dict[str, Any]],
        impacted_entities: list[dict[str, Any]],
        affected_paths: list[dict[str, Any]],
        support_signals: list[dict[str, Any]] | None = None,
        contradiction_signals: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        run_id = f"scenariorun:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scenario_runs (
                    run_id, scenario_id, run_summary, assumptions_json, impacted_entities_json,
                    affected_paths_json, support_signals_json, contradiction_signals_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    scenario_id,
                    _clean_text(run_summary),
                    json.dumps(assumptions),
                    json.dumps(impacted_entities),
                    json.dumps(affected_paths),
                    json.dumps(support_signals or []),
                    json.dumps(contradiction_signals or []),
                    now,
                ),
            )
            connection.execute(
                "UPDATE scenarios SET updated_at_utc = ? WHERE scenario_id = ?",
                (now, scenario_id),
            )
            row = connection.execute(
                "SELECT * FROM scenario_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return {} if row is None else _row_to_dict(row)

    def list_scenario_runs(self, scenario_id: str, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scenario_runs
                WHERE scenario_id = ?
                ORDER BY created_at_utc DESC
                LIMIT ?
                """,
                (scenario_id, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_scenario_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scenario_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def list_theses(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    theses.*,
                    COUNT(DISTINCT thesis_links.link_id) AS link_count,
                    COUNT(DISTINCT thesis_updates.update_id) AS update_count
                FROM theses
                LEFT JOIN thesis_links ON thesis_links.thesis_id = theses.thesis_id
                LEFT JOIN thesis_updates ON thesis_updates.thesis_id = theses.thesis_id
                GROUP BY theses.thesis_id
                ORDER BY theses.updated_at_utc DESC, theses.title ASC
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def create_thesis(
        self,
        title: str,
        statement: str,
        stance: str = "mixed",
        confidence: float = 0.5,
        status: str = "active",
        time_horizon: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        thesis_id = f"thesis:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO theses (
                    thesis_id, title, statement, stance, confidence, status, time_horizon, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thesis_id,
                    title.strip(),
                    statement.strip(),
                    stance,
                    confidence,
                    status,
                    _clean_text(time_horizon),
                    now,
                    now,
                ),
            )
        return self.get_thesis(thesis_id) or {}

    def get_thesis(self, thesis_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM theses WHERE thesis_id = ?",
                (thesis_id,),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def list_thesis_links(self, thesis_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM thesis_links
                WHERE thesis_id = ?
                ORDER BY created_at_utc ASC, label ASC, item_id_value ASC
                """,
                (thesis_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def add_thesis_link(
        self,
        thesis_id: str,
        item_type: str,
        item_id_value: str,
        relationship: str = "supports",
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        existing = self._find_thesis_link(thesis_id, item_type, item_id_value, relationship)
        if existing is not None:
            return existing
        link_id = f"thesislink:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO thesis_links (
                    link_id, thesis_id, item_type, item_id_value, relationship, label, metadata_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    link_id,
                    thesis_id,
                    item_type,
                    item_id_value,
                    relationship,
                    _clean_text(label),
                    json.dumps(metadata or {}),
                    now,
                ),
            )
            connection.execute(
                "UPDATE theses SET updated_at_utc = ? WHERE thesis_id = ?",
                (now, thesis_id),
            )
            row = connection.execute(
                "SELECT * FROM thesis_links WHERE link_id = ?",
                (link_id,),
            ).fetchone()
        return {} if row is None else _row_to_dict(row)

    def list_thesis_updates(self, thesis_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM thesis_updates
                WHERE thesis_id = ?
                ORDER BY created_at_utc DESC
                """,
                (thesis_id,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def add_thesis_update(
        self,
        thesis_id: str,
        summary: str,
        confidence: float | None = None,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        update_id = f"thesisupdate:{uuid4().hex[:12]}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO thesis_updates (
                    update_id, thesis_id, summary, confidence, created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (update_id, thesis_id, summary.strip(), confidence, now),
            )
            if confidence is None:
                connection.execute(
                    "UPDATE theses SET updated_at_utc = ? WHERE thesis_id = ?",
                    (now, thesis_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE theses
                    SET confidence = ?, updated_at_utc = ?
                    WHERE thesis_id = ?
                    """,
                    (confidence, now, thesis_id),
                )
            row = connection.execute(
                "SELECT * FROM thesis_updates WHERE update_id = ?",
                (update_id,),
            ).fetchone()
        return {} if row is None else _row_to_dict(row)

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        existing = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _find_watchlist_item(
        self,
        watchlist_id: str,
        item_type: str,
        item_id_value: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM watchlist_items
                WHERE watchlist_id = ? AND item_type = ? AND item_id_value = ?
                """,
                (watchlist_id, item_type, item_id_value),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def _find_scenario_assumption(
        self,
        scenario_id: str,
        item_type: str,
        item_id_value: str,
        expected_direction: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM scenario_assumptions
                WHERE scenario_id = ? AND item_type = ? AND item_id_value = ? AND expected_direction = ?
                """,
                (scenario_id, item_type, item_id_value, expected_direction),
            ).fetchone()
        return None if row is None else _row_to_dict(row)

    def _find_scenario_monitor(
        self,
        scenario_id: str,
        item_type: str,
        item_id_value: str,
        expected_direction: str | None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM scenario_monitors
            WHERE scenario_id = ? AND item_type = ? AND item_id_value = ?
        """
        params: list[Any] = [scenario_id, item_type, item_id_value]
        if expected_direction is None:
            query += " AND expected_direction IS NULL"
        else:
            query += " AND expected_direction = ?"
            params.append(expected_direction)
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return None if row is None else _row_to_dict(row)

    def _find_thesis_link(
        self,
        thesis_id: str,
        item_type: str,
        item_id_value: str,
        relationship: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM thesis_links
                WHERE thesis_id = ? AND item_type = ? AND item_id_value = ? AND relationship = ?
                """,
                (thesis_id, item_type, item_id_value, relationship),
            ).fetchone()
        return None if row is None else _row_to_dict(row)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    for key, value in list(payload.items()):
        if value is None:
            continue
        if key.endswith("_json"):
            try:
                payload[key] = json.loads(value)
            except json.JSONDecodeError:
                payload[key] = value
    return payload
