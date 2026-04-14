from __future__ import annotations

from typing import Any

from semicon_alpha.appstate import AppStateRepository


class NotesService:
    def __init__(self, appstate: AppStateRepository) -> None:
        self.appstate = appstate

    def list_notes(
        self,
        subject_type: str | None = None,
        subject_id: str | None = None,
        board_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.appstate.list_notes(subject_type=subject_type, subject_id=subject_id, board_id=board_id)

    def create_note(
        self,
        subject_type: str,
        subject_id: str,
        body: str,
        title: str | None = None,
        stance: str | None = None,
        board_id: str | None = None,
    ) -> dict[str, Any]:
        return self.appstate.create_note(
            subject_type=subject_type,
            subject_id=subject_id,
            body=body,
            title=title,
            stance=stance,
            board_id=board_id,
        )
