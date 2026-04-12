from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import yaml


def discover_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    candidates = [current, *current.parents]
    markers = ("pyproject.toml", "zervehack_semiconductor_project_plan.md")
    for candidate in candidates:
        if any((candidate / marker).exists() for marker in markers):
            return candidate
    return current


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def stable_id(prefix: str, *parts: object) -> str:
    payload = "||".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-")


def normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def write_text(path: Path, contents: str) -> Path:
    ensure_dir(path.parent)
    path.write_text(contents, encoding="utf-8")
    return path


def write_bytes(path: Path, contents: bytes) -> Path:
    ensure_dir(path.parent)
    path.write_bytes(contents)
    return path


def write_json(path: Path, payload: object) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def records_to_dataframe(records: Iterable[object]) -> pd.DataFrame:
    flattened: list[dict] = []
    for record in records:
        if hasattr(record, "as_flat_dict"):
            payload = record.as_flat_dict()
        elif isinstance(record, dict):
            payload = record
        else:
            raise TypeError(f"Unsupported record type: {type(record)!r}")
        flattened.append({key: _serialize_for_frame(value) for key, value in payload.items()})
    return pd.DataFrame(flattened)


def _serialize_for_frame(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list | dict):
        return json.dumps(value, sort_keys=True)
    return value


def upsert_parquet(
    path: Path,
    records: Iterable[object],
    unique_keys: list[str],
    sort_by: list[str] | None = None,
) -> pd.DataFrame:
    new_frame = records_to_dataframe(records)
    if new_frame.empty:
        if path.exists():
            return pd.read_parquet(path)
        return new_frame
    if path.exists():
        combined = pd.concat([pd.read_parquet(path), new_frame], ignore_index=True)
    else:
        combined = new_frame
    if sort_by:
        combined = combined.sort_values(sort_by)
    combined = combined.drop_duplicates(subset=unique_keys, keep="last").reset_index(drop=True)
    ensure_dir(path.parent)
    combined.to_parquet(path, index=False)
    return combined
