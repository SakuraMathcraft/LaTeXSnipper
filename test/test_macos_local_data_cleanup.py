from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_macos_cleanup_targets_are_user_library_app_owned_paths(tmp_path, monkeypatch) -> None:
    from runtime import macos_local_data_cleanup as cleanup

    monkeypatch.setattr(cleanup.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))

    targets = cleanup.macos_cleanup_targets()

    assert targets == [
        tmp_path / "Library" / "Application Support" / "LaTeXSnipper" / "deps",
        tmp_path / "Library" / "Caches" / "LaTeXSnipper",
        tmp_path / "Library" / "Logs" / "LaTeXSnipper",
    ]
    assert cleanup.macos_cleanup_targets(include_config=True)[-1] == (
        tmp_path / "Library" / "Application Support" / "LaTeXSnipper"
    )
    assert all(target.is_relative_to(tmp_path / "Library") for target in targets)


def test_macos_cleanup_removes_downloaded_deps_cache_and_logs_but_keeps_config(
    tmp_path, monkeypatch
) -> None:
    from runtime import macos_local_data_cleanup as cleanup

    monkeypatch.setattr(cleanup.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))

    support_dir = tmp_path / "Library" / "Application Support" / "LaTeXSnipper"
    deps_dir = support_dir / "deps"
    cache_dir = tmp_path / "Library" / "Caches" / "LaTeXSnipper"
    log_dir = tmp_path / "Library" / "Logs" / "LaTeXSnipper"
    config_file = support_dir / "LaTeXSnipper_config.json"
    for directory in (deps_dir, cache_dir, log_dir):
        directory.mkdir(parents=True)
        (directory / "sample.txt").write_text("local data", encoding="utf-8")
    config_file.write_text("{}", encoding="utf-8")

    result = cleanup.cleanup_macos_local_data()

    assert result.failed == []
    assert str(deps_dir) in result.removed
    assert str(cache_dir) in result.removed
    assert str(log_dir) in result.removed
    assert not deps_dir.exists()
    assert not cache_dir.exists()
    assert not log_dir.exists()
    assert config_file.exists()


def test_macos_cleanup_is_noop_on_other_platforms(tmp_path, monkeypatch) -> None:
    from runtime import macos_local_data_cleanup as cleanup

    monkeypatch.setattr(cleanup.sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))

    assert cleanup.macos_cleanup_targets() == []
    result = cleanup.cleanup_macos_local_data()
    assert result.removed == []
    assert result.failed == []


def test_macos_cleanup_ui_is_platform_scoped() -> None:
    settings_layout = (ROOT / "src" / "ui" / "settings_layout_builder.py").read_text(encoding="utf-8")
    settings_env = (ROOT / "src" / "ui" / "settings_environment_mixin.py").read_text(encoding="utf-8")
    deps_ui = (ROOT / "src" / "bootstrap" / "deps_ui.py").read_text(encoding="utf-8")

    assert "btn_cleanup_macos_local_data" in settings_layout
    assert "sys.platform == \"darwin\"" in settings_layout
    assert "_cleanup_macos_local_data" in settings_env
    assert "清理本机依赖与缓存" in settings_layout
    assert "btn_cleanup_macos_local_data" in deps_ui
    assert "cleanup_macos_local_data" in deps_ui
