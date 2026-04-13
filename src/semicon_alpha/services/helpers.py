from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import pandas as pd


def parse_json_value(value: Any, default: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, (list, dict)):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def parse_json_list(value: Any) -> list[str]:
    parsed = parse_json_value(value, None)
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    if parsed is None:
        text = str(value).strip() if value is not None else ""
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]
    return [str(parsed)]


def to_optional_datetime(value: Any) -> datetime | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def to_optional_date(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def coerce_optional_str(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def entity_id_to_ticker(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(":", 1)[1] if ":" in value else value


def clean_record(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, float) and pd.isna(value):
            cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned


def has_columns(frame: pd.DataFrame, *columns: str) -> bool:
    if frame.empty and len(frame.columns) == 0:
        return False
    available = set(frame.columns)
    return all(column in available for column in columns)
