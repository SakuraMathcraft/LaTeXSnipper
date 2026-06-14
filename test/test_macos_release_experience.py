from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


def _reload_module(name: str):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_macos_app_paths_use_library_dirs_and_migrate_small_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))

    legacy = tmp_path / ".latexsnipper"
    legacy.mkdir()
    (legacy / "history.json").write_text('{"history": ["x"]}', encoding="utf-8")
    (legacy / "favorites.json").write_text('{"favorites": ["x"]}', encoding="utf-8")
    (legacy / "latex_settings.json").write_text("{}", encoding="utf-8")
    (legacy / "LaTeXSnipper_config.json").write_text(
        json.dumps(
            {
                "history_path": str(legacy / "history.json"),
                "favorites_path": str(legacy / "favorites.json"),
                "install_base_dir": str(legacy / "deps"),
            }
        ),
        encoding="utf-8",
    )

    app_paths = _reload_module("runtime.app_paths")

    state_dir = app_paths.app_state_dir()
    assert state_dir == tmp_path / "Library" / "Application Support" / "LaTeXSnipper"
    assert app_paths.app_cache_dir() == tmp_path / "Library" / "Caches" / "LaTeXSnipper"
    assert app_paths.app_log_dir() == tmp_path / "Library" / "Logs" / "LaTeXSnipper"
    assert (state_dir / "history.json").read_text(encoding="utf-8") == '{"history": ["x"]}'
    assert (state_dir / "favorites.json").is_file()
    assert (state_dir / "latex_settings.json").is_file()

    migrated_config = json.loads((state_dir / "LaTeXSnipper_config.json").read_text(encoding="utf-8"))
    assert migrated_config["history_path"] == str(state_dir / "history.json")
    assert migrated_config["favorites_path"] == str(state_dir / "favorites.json")
    assert migrated_config["install_base_dir"] == str(legacy / "deps")


def test_macos_mathcraft_models_default_to_application_support(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("MATHCRAFT_HOME", raising=False)

    cache = _reload_module("mathcraft_ocr.cache")

    assert cache.default_user_models_dir() == (
        tmp_path / "Library" / "Application Support" / "LaTeXSnipper" / "MathCraft" / "models"
    )

    monkeypatch.setenv("MATHCRAFT_HOME", str(tmp_path / "custom-models"))
    assert cache.resolve_user_models_dir() == tmp_path / "custom-models"


def test_update_cache_uses_cache_directory(tmp_path, monkeypatch) -> None:
    installer_cache = _reload_module("update.installer_cache")
    monkeypatch.setattr(installer_cache, "app_cache_dir", lambda: tmp_path)

    assert installer_cache._update_dir() == tmp_path / "updates"
    assert (tmp_path / "updates").is_dir()


def test_macos_update_assets_open_with_finder(tmp_path, monkeypatch) -> None:
    launcher = _reload_module("update.downloaded_asset_launcher")
    dmg = tmp_path / "LaTeXSnipper_2.4.0_arm64.dmg"
    dmg.write_bytes(b"dmg")
    calls: list[list[str]] = []

    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args, **_kwargs: calls.append(args))

    assert launcher.update_asset_action(dmg, platform="darwin") == "open_macos_package"
    assert launcher.open_downloaded_update_asset(dmg, platform="darwin") is True
    assert calls == [["open", str(dmg)]]
    assert "Applications" in launcher.macos_update_guidance(dmg)


def test_macos_system_python_hint_scopes_python_to_optional_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    deps_entry = _reload_module("bootstrap.deps_entry")

    hint = deps_entry._system_python_install_hint("未找到系统 Python 3")

    assert "主程序可继续运行" in hint
    assert "可选依赖功能" in hint
    assert "brew install python" in hint
    assert "python.org" in hint
