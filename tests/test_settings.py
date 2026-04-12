from pathlib import Path

from semicon_alpha.settings import Settings


def test_storage_root_is_resolved_relative_to_project_root():
    settings = Settings(SEMICON_ALPHA_STORAGE_ROOT="runtime")
    assert settings.runtime_root == (settings.project_root / "runtime").resolve()
    assert settings.data_dir == settings.runtime_root / "data"
