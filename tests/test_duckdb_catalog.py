from semicon_alpha.settings import Settings
from semicon_alpha.storage import DuckDBCatalog
from semicon_alpha.utils.io import upsert_parquet


def test_duckdb_catalog_exposes_processed_parquet_as_views(tmp_path):
    settings = Settings(project_root=tmp_path)
    settings.ensure_directories()

    upsert_parquet(
        settings.processed_dir / "sample_dataset.parquet",
        [{"id": "a", "value": 1}, {"id": "b", "value": 2}],
        unique_keys=["id"],
    )

    catalog = DuckDBCatalog(settings)
    result = catalog.refresh_processed_views()

    assert result["dataset_count"] == 1

    import duckdb

    with duckdb.connect(str(settings.duckdb_path)) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM sample_dataset").fetchone()[0]
        manifest = connection.execute(
            "SELECT dataset_name, row_count FROM dataset_catalog WHERE dataset_name = 'sample_dataset'"
        ).fetchone()

    assert rows == 2
    assert manifest == ("sample_dataset", 2)
