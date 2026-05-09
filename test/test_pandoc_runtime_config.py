# coding: utf-8
# ruff: noqa: E402

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from runtime import pandoc_runtime


def test_pandoc_path_persists_in_app_config(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "LaTeXSnipper_config.json"
    pandoc_exe = tmp_path / "pandoc.exe"
    pandoc_exe.write_text("stub", encoding="utf-8")

    monkeypatch.setattr(pandoc_runtime, "app_config_path", lambda: cfg_path)

    pandoc_runtime.save_configured_pandoc_path(pandoc_exe)

    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert data[pandoc_runtime.PANDOC_EXECUTABLE_CONFIG_KEY] == str(pandoc_exe.resolve())
    assert pandoc_runtime.load_configured_pandoc_path() == pandoc_exe

    pandoc_runtime.clear_configured_pandoc_path()
    cleaned = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert pandoc_runtime.PANDOC_EXECUTABLE_CONFIG_KEY not in cleaned


def test_missing_configured_pandoc_path_is_ignored(tmp_path, monkeypatch) -> None:
    cfg_path = tmp_path / "LaTeXSnipper_config.json"
    cfg_path.write_text(
        json.dumps({pandoc_runtime.PANDOC_EXECUTABLE_CONFIG_KEY: str(tmp_path / "missing.exe")}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pandoc_runtime, "app_config_path", lambda: cfg_path)

    assert pandoc_runtime.load_configured_pandoc_path() is None
