from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb

from semicon_alpha.settings import Settings
from semicon_alpha.utils.io import ensure_dir


class DuckDBCatalog:
    """Expose processed parquet datasets as queryable DuckDB views."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.duckdb_path

    def refresh_processed_views(self) -> dict[str, int]:
        datasets = sorted(self.settings.processed_dir.glob("*.parquet"))
        ensure_dir(self.db_path.parent)
        dataset_count = 0
        with duckdb.connect(str(self.db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dataset_catalog (
                    dataset_name VARCHAR PRIMARY KEY,
                    dataset_path VARCHAR NOT NULL,
                    row_count BIGINT NOT NULL,
                    refreshed_at_utc TIMESTAMP NOT NULL
                )
                """
            )
            for dataset_path in datasets:
                self._refresh_dataset(connection, dataset_path.stem, dataset_path)
                dataset_count += 1
        return {"dataset_count": dataset_count}

    def _refresh_dataset(
        self, connection: duckdb.DuckDBPyConnection, dataset_name: str, dataset_path: Path
    ) -> None:
        path_string = str(dataset_path.resolve()).replace("'", "''")
        view_name = _safe_identifier(dataset_name)
        row_count = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?)",
            [str(dataset_path.resolve())],
        ).fetchone()[0]
        connection.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS "
            f"SELECT * FROM read_parquet('{path_string}')"
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO dataset_catalog (
                dataset_name,
                dataset_path,
                row_count,
                refreshed_at_utc
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                dataset_name,
                str(dataset_path.resolve()),
                row_count,
                datetime.now(timezone.utc).replace(tzinfo=None),
            ],
        )


def _safe_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
