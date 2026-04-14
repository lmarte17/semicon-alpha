from __future__ import annotations

from pathlib import Path
from typing import Iterable

from semicon_alpha.utils.io import ensure_dir, write_text


class GeminiBatchRequestBuilder:
    def write_jsonl(self, path: Path, requests: Iterable[dict]) -> Path:
        ensure_dir(path.parent)
        lines = [self._serialize_request(request) for request in requests]
        return write_text(path, "\n".join(lines) + ("\n" if lines else ""))

    def _serialize_request(self, request: dict) -> str:
        import json

        return json.dumps(request, sort_keys=True)
