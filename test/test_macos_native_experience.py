from __future__ import annotations

from runtime import app_paths


def test_macos_app_paths_use_library_directories(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_paths.sys, "platform", "darwin")
    monkeypatch.setattr(app_paths.pathlib.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(app_paths, "_APP_STATE_DIR_CACHE", None)
    monkeypatch.setattr(app_paths, "_APP_LOG_DIR_CACHE", None)

    assert (
        app_paths.app_state_dir()
        == tmp_path / "Library" / "Application Support" / "LaTeXSnipper"
    )
    assert app_paths.app_cache_dir() == tmp_path / "Library" / "Caches" / "LaTeXSnipper"
    assert app_paths.app_log_dir() == tmp_path / "Library" / "Logs" / "LaTeXSnipper"
    assert app_paths.app_config_path() == (
        tmp_path
        / "Library"
        / "Application Support"
        / "LaTeXSnipper"
        / "LaTeXSnipper_config.json"
    )
